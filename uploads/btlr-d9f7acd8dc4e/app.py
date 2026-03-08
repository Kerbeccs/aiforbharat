"""
Ride Scheduling Dashboard Backend
Integrates with Django REST API for supervisor webapp
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import json
import requests
from mock_data import ESCORTS_DATA
from assignment_logic import (
    assign_passengers_optimally, 
    assign_escort_to_driver, 
    manual_assign_passenger,
    format_mappings_for_django_api,
    Driver,
    Passenger
)
from django_api_client import DjangoAPIClient, OFFICE_LOCATION

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend-backend communication

# Initialize Django API client
# For demo mode, JWT token is optional
django_client = DjangoAPIClient()

# Store current assignment state (for manual assignment and escort assignment)
current_assignment_state = {
    'drivers': [],
    'passengers': [],
    'result': None,
    'mappings': []
}


@app.route('/')
def index():
    """
    Render the main dashboard page
    """
    return render_template('index.html')


@app.route('/api/people', methods=['GET'])
def get_people():
    """
    API endpoint to get passengers from Django API
    Query params: date, shift, trip_direction
    """
    try:
        date = request.args.get('date')
        shift = request.args.get('shift', type=int)
        trip_direction = request.args.get('trip_direction', type=int)
        
        if not date or not shift or not trip_direction:
            return jsonify({'error': 'Missing required parameters: date, shift, trip_direction'}), 400
        
        # Fetch from Django API
        passengers = django_client.get_passengers(date, shift, trip_direction)
        
        # Transform to format expected by frontend
        formatted_passengers = []
        for p in passengers:
            formatted_passengers.append({
                'id': p.get('id'),
                'name': p.get('name', ''),
                'location': p.get('home_address', ''),
                'coordinates': [p.get('home_lat', 0), p.get('home_lng', 0)],
                'gender': 1 if p.get('gender') == 'F' else 0,
                'phone': p.get('phone'),
                'is_adhoc': p.get('is_adhoc', False)
            })
        
        return jsonify(formatted_passengers)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/drivers', methods=['GET'])
def get_drivers():
    """
    API endpoint to get drivers from Django API
    Query params: active (optional, defaults to true)
    """
    try:
        active = request.args.get('active', 'true').lower() == 'true'
        
        # Fetch from Django API
        drivers = django_client.get_drivers(active=active)
        
        # Transform to format expected by frontend
        formatted_drivers = []
        for d in drivers:
            formatted_drivers.append({
                'id': d.get('id'),
                'name': d.get('name', ''),
                'location': d.get('home_address', ''),
                'coordinates': [d.get('home_lat', 0), d.get('home_lng', 0)],
                'capacity': d.get('capacity', 5),
                'cab_number': d.get('cab_number', ''),
                'phone': d.get('phone'),
                'is_active': d.get('is_active', True),
                'is_online': d.get('is_online', False)
            })
        
        return jsonify(formatted_drivers)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/escorts')
def get_escorts():
    """
    API endpoint to get all escorts data
    """
    return jsonify(ESCORTS_DATA)


@app.route('/api/supervisor/drivers', methods=['GET'])
def get_supervisor_drivers():
    """
    API endpoint to get detailed driver information including device_id for video feed
    This fetches full driver details from Django API
    """
    try:
        # Fetch from Django API
        drivers = django_client.get_drivers(active=None)  # Get all drivers
        
        # Return full driver details including device_id
        return jsonify(drivers)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/master-data/passengers', methods=['GET'])
def get_master_data_passengers():
    """
    Get all passengers for Master Data by fetching for all shift/direction combinations
    for a given date and merging (deduplicate by id).
    Query params: date (YYYY-MM-DD, default: today)
    """
    try:
        date = request.args.get('date')
        if not date:
            from datetime import date as date_type
            date = date_type.today().isoformat()
        
        seen_ids = set()
        merged = []
        for shift in (1, 2):
            for trip_direction in (1, 2):
                try:
                    passengers = django_client.get_passengers(date, shift, trip_direction)
                    for p in passengers:
                        pid = p.get('id')
                        if pid is not None and pid not in seen_ids:
                            seen_ids.add(pid)
                            merged.append(p)
                except Exception:
                    continue
        return jsonify({'passengers': merged, 'date': date})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/video/token', methods=['GET'])
def get_video_token():
    """
    API endpoint to get X-Token for video stream authentication
    This calls the video API login endpoint
    """
    try:
        # Video API login endpoint
        video_api_url = "http://103.55.89.243:9337/api/v1/user/login"
        
        # Login credentials for video API
        credentials = {
            "username": "proroute",
            "password": "0f722f7b5804e22be1fb47635698e151",
            "model": "web",
            "progVersion": "0.0.1",
            "platform": 3
        }
        
        # Make login request
        import requests
        response = requests.post(
            video_api_url,
            json=credentials,
            headers={'Content-Type': 'application/json'},
            timeout=10,
            verify=False
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract token from response
            token = None
            if 'token' in data:
                token = data['token']
            elif 'data' in data and isinstance(data['data'], dict):
                if 'token' in data['data']:
                    token = data['data']['token']
                elif 'X-Token' in data['data']:
                    token = data['data']['X-Token']
            elif 'X-Token' in data:
                token = data['X-Token']
            
            if token:
                return jsonify({
                    'success': True,
                    'token': token
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Could not extract token from response'
                }), 500
        else:
            return jsonify({
                'success': False,
                'error': f'Login failed with status {response.status_code}'
            }), 500
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/video/stream/<device_id>', methods=['GET'])
def get_video_stream(device_id):
    """
    API endpoint to get video stream URL for a specific device
    Returns the HLS stream URL that can be used in video player
    """
    try:
        # Base URL for video streams
        base_url = "http://103.55.89.243:9330"
        
        # Channel number (default to 1, can be made configurable)
        channel = request.args.get('channel', '1')
        
        # Construct stream URL
        stream_url = f"{base_url}/rtp/{device_id}_{channel}/hls.m3u8"
        
        return jsonify({
            'success': True,
            'stream_url': stream_url,
            'device_id': device_id,
            'channel': channel
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/assign-drivers', methods=['POST'])
def assign_drivers():
    """
    API endpoint to perform driver-passenger assignment using distance-based algorithm
    Expects JSON with: date, shift, trip_direction, selected_people_ids (optional), selected_driver_ids (optional)
    If selected_people_ids/driver_ids not provided, uses all from API
    """
    try:
        data = request.get_json()
        date = data.get('date')
        shift = data.get('shift')
        trip_direction = data.get('trip_direction')
        selected_people_ids = data.get('selected_people_ids', [])
        selected_driver_ids = data.get('selected_driver_ids', [])
        base_pickup_time = data.get('base_pickup_time', '08:00:00')
        time_interval = data.get('time_interval_minutes', 15)
        
        # Convert to int if provided
        if shift is not None:
            shift = int(shift)
        if trip_direction is not None:
            trip_direction = int(trip_direction)
        
        # Validate input
        if not date or shift is None or trip_direction is None:
            return jsonify({'error': 'Missing required data: date, shift, trip_direction'}), 400
        
        # Fetch passengers and drivers from Django API
        try:
            all_passengers = django_client.get_passengers(date, shift, trip_direction)
            all_drivers = django_client.get_drivers(active=True)
        except Exception as e:
            return jsonify({'error': f'Failed to fetch data from Django API: {str(e)}'}), 500
        
        # Filter if IDs provided
        if selected_people_ids:
            all_passengers = [p for p in all_passengers if p.get('id') in selected_people_ids]
        if selected_driver_ids:
            all_drivers = [d for d in all_drivers if d.get('id') in selected_driver_ids]
        
        if not all_passengers:
            return jsonify({'error': 'No passengers found for the selected criteria'}), 400
        if not all_drivers:
            return jsonify({'error': 'No active drivers found'}), 400
        
        # Transform to format expected by assignment logic
        passengers_data = []
        for p in all_passengers:
            # Ensure coordinates are floats, not strings
            home_lat = float(p.get('home_lat', 0)) if p.get('home_lat') is not None else 0.0
            home_lng = float(p.get('home_lng', 0)) if p.get('home_lng') is not None else 0.0
            passengers_data.append({
                'id': p.get('id'),
                'name': p.get('name', ''),
                'coordinates': [home_lat, home_lng],
                'gender': 1 if p.get('gender') == 'F' else 0,
                'home_lat': home_lat,
                'home_lng': home_lng,
                'home_address': p.get('home_address', '')
            })
        
        drivers_data = []
        for d in all_drivers:
            # Ensure coordinates are floats, not strings
            home_lat = float(d.get('home_lat', 0)) if d.get('home_lat') is not None else 0.0
            home_lng = float(d.get('home_lng', 0)) if d.get('home_lng') is not None else 0.0
            drivers_data.append({
                'id': d.get('id'),
                'coordinates': [home_lat, home_lng],
                'capacity': int(d.get('capacity', 5)),
                'name': d.get('name', ''),
                'home_lat': home_lat,
                'home_lng': home_lng
            })
        
        # Perform assignment using the new logic
        result = assign_passengers_optimally(drivers_data, passengers_data)
        
        # Store state for manual assignment and escort assignment
        current_assignment_state['drivers'] = result.drivers
        current_assignment_state['passengers'] = passengers_data
        current_assignment_state['result'] = result
        current_assignment_state['drivers_data'] = drivers_data  # Store for escort assignment
        current_assignment_state['date'] = date
        current_assignment_state['shift'] = shift
        current_assignment_state['trip_direction'] = trip_direction
        current_assignment_state['drivers_data'] = drivers_data  # Store for escort assignment
        
        # Format mappings for Django API
        mappings = format_mappings_for_django_api(
            result=result,
            passengers_data=passengers_data,
            drivers_data=drivers_data,
            ride_date=date,
            shift=shift,
            trip_direction=trip_direction,
            office_location=OFFICE_LOCATION,
            base_pickup_time=base_pickup_time,
            time_interval_minutes=time_interval,
            escorts_data=ESCORTS_DATA
        )
        
        current_assignment_state['mappings'] = mappings
        
        # Convert result to JSON-serializable format for display
        assignments = []
        for driver in result.drivers:
            for passenger_id in driver.assigned_passengers:
                passenger = next((p for p in passengers_data if p['id'] == passenger_id), None)
                if passenger:
                    import math
                    dist = math.hypot(
                        passenger['coordinates'][1] - driver.x,
                        passenger['coordinates'][0] - driver.y
                    ) * 111  # Convert to km
                    
                    assignments.append({
                        'person': passenger,
                        'driver': next((d for d in drivers_data if d['id'] == driver.id), {}),
                        'distance_km': round(dist, 2),
                        'date': date
                    })
        
        # Format unassigned passengers with full details
        unassigned = []
        for unassigned_p in result.unassigned_passengers:
            passenger = next((p for p in passengers_data if p['id'] == unassigned_p.id), None)
            if passenger:
                unassigned.append({
                    **passenger,
                    'unassigned_reason': unassigned_p.unassigned_reason
                })
        
        # Format driver assignments with full details
        driver_assignments = []
        for driver in result.drivers:
            driver_data = next((d for d in drivers_data if d['id'] == driver.id), {})
            driver_assignments.append({
                'driver': driver_data,
                'used_seats': driver.used_seats,
                'capacity': driver.capacity,
                'female_count': driver.female_count,
                'male_count': driver.male_count,
                'total_distance': round(driver.total_distance * 111, 2),  # Convert to km
                'passenger_ids': driver.assigned_passengers,
                'needs_escort': driver.female_count > 0 and driver.male_count == 0,
                'escort_id': driver.escort_id
            })
        
        return jsonify({
            'assignments': assignments,
            'unassigned_passengers': unassigned,
            'driver_assignments': driver_assignments,
            'all_assigned': result.all_assigned,
            'summary': result.summary,
            'date': date,
            'shift': shift,
            'trip_direction': trip_direction,
            'mappings': mappings  # Include mappings ready for Django API
        })
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in assign_drivers: {error_trace}")  # Print to console for debugging
        return jsonify({'error': str(e), 'traceback': error_trace}), 500


@app.route('/api/send-mappings', methods=['POST'])
def send_mappings():
    """
    Send mappings to Django API to create rides
    Expects JSON with: date, shift, trip_direction, mappings (optional - uses stored if not provided)
    """
    try:
        data = request.get_json()
        date = data.get('date')
        shift = data.get('shift')
        trip_direction = data.get('trip_direction')
        mappings = data.get('mappings')
        
        # Convert to int if provided
        if shift is not None:
            shift = int(shift)
        if trip_direction is not None:
            trip_direction = int(trip_direction)
        
        # Validate input
        if not date or shift is None or trip_direction is None:
            return jsonify({'error': 'Missing required data: date, shift, trip_direction'}), 400
        
        # Always use stored mappings (they have the latest escort assignments)
        # Frontend mappings might be outdated
        mappings = current_assignment_state.get('mappings', [])
        
        if not mappings:
            return jsonify({'error': 'No mappings to send. Please run assignment first.'}), 400
        
        # Debug: Print all mappings being sent
        print(f"\n=== SENDING MAPPINGS TO DJANGO API ===")
        print(f"Total mappings: {len(mappings)}")
        print(f"Date: {date}, Shift: {shift}, Direction: {trip_direction}")
        print(f"\nFull mappings JSON:")
        import json
        print(json.dumps(mappings, indent=2, default=str))
        
        escort_count = 0
        for i, m in enumerate(mappings):
            if m.get('escort_name') and m.get('escort_name') != '0':
                escort_count += 1
                print(f"\n  Mapping {i} WITH ESCORT:")
                print(f"    driver_id={m.get('driver_id')}, passenger_id={m.get('passenger_id')}, sequence={m.get('sequence_order')}")
                print(f"    escort_name='{m.get('escort_name')}', escort_id={m.get('escort_id')}")
        
        print(f"\nTotal mappings with escorts: {escort_count}")
        print(f"=== END SEND DEBUG ===\n")
        
        # Validate mappings before sending
        for i, mapping in enumerate(mappings):
            required_fields = ['driver_id', 'passenger_id', 'sequence_order', 'pickup_lat', 'pickup_lng', 
                             'drop_lat', 'drop_lng', 'scheduled_pickup_time', 'escort_name']
            missing = [field for field in required_fields if field not in mapping or mapping[field] is None]
            if missing:
                return jsonify({
                    'error': f'Mapping {i} is missing required fields: {", ".join(missing)}',
                    'mapping': mapping
                }), 400
        
        # Send to Django API
        try:
            response = django_client.create_rides(date, shift, trip_direction, mappings)
            return jsonify({
                'success': True,
                'message': response.get('message', 'Rides created successfully'),
                'ride_ids': response.get('ride_ids', []),
                'response': response
            })
        except Exception as e:
            error_msg = str(e)
            # Log full error for debugging
            import traceback
            print(f"\n=== DJANGO API ERROR ===")
            print(f"Error: {error_msg}")
            print(f"Traceback: {traceback.format_exc()}")
            print(f"=== END ERROR ===\n")
            return jsonify({'error': f'Failed to create rides in Django API: {error_msg}'}), 500
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduled-rides', methods=['GET'])
def get_scheduled_rides():
    """
    Get scheduled rides from Django API
    Query params: date, start_date, end_date, shift, trip_direction, status, driver_id (all optional)
    """
    try:
        date = request.args.get('date')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        shift = request.args.get('shift')
        trip_direction = request.args.get('trip_direction')
        status = request.args.get('status')
        driver_id = request.args.get('driver_id')
        
        # Convert to int if provided
        shift_int = int(shift) if shift else None
        trip_direction_int = int(trip_direction) if trip_direction else None
        status_int = int(status) if status else None
        driver_id_int = int(driver_id) if driver_id else None
        
        # Fetch from Django API
        response = django_client.get_rides(
            date=date,
            start_date=start_date,
            end_date=end_date,
            shift=shift_int,
            trip_direction=trip_direction_int,
            status=status_int,
            driver_id=driver_id_int,
        )
        
        return jsonify(response)
    
    except Exception as e:
        import traceback
        print(f"Error in get_scheduled_rides: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/manual-assign', methods=['POST'])
def manual_assign():
    """
    API endpoint for manual assignment of passengers to drivers
    Expects JSON with: passenger_id, driver_id
    """
    try:
        data = request.get_json()
        passenger_id = data.get('passenger_id')
        driver_id = data.get('driver_id')
        
        if not passenger_id or not driver_id:
            return jsonify({'error': 'Missing passenger_id or driver_id'}), 400
        
        if not current_assignment_state['result']:
            return jsonify({'error': 'No active assignment. Please run assignment first.'}), 400
        
        # Get passenger and driver from stored state
        passengers_data = current_assignment_state['passengers']
        drivers = current_assignment_state['drivers']
        
        # Find the passenger in the stored result
        passenger_obj = None
        for unassigned_p in current_assignment_state['result'].unassigned_passengers:
            if unassigned_p.id == passenger_id:
                passenger_obj = unassigned_p
                break
        
        # If not found in unassigned, create new passenger object
        if not passenger_obj:
            passenger_data = next((p for p in passengers_data if p['id'] == passenger_id), None)
            if not passenger_data:
                return jsonify({'error': 'Passenger not found'}), 400
            
            passenger_obj = Passenger(
                id=passenger_data['id'],
                x=passenger_data.get('home_lng', passenger_data.get('coordinates', [0, 0])[1]),
                y=passenger_data.get('home_lat', passenger_data.get('coordinates', [0, 0])[0]),
                gender=passenger_data.get('gender', 0),
                name=passenger_data.get('name', ''),
                location=passenger_data.get('home_address', '')
            )
        
        result = manual_assign_passenger(passenger_id, driver_id, drivers, [passenger_obj])
        
        if result['success']:
            # Remove from unassigned list if present
            current_assignment_state['result'].unassigned_passengers = [
                p for p in current_assignment_state['result'].unassigned_passengers 
                if p.id != passenger_id
            ]
            
            # Update stored state
            current_assignment_state['drivers'] = drivers
            
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/assign-escort', methods=['POST'])
def assign_escort():
    """
    API endpoint to assign an escort to a driver
    Expects JSON with: driver_id, escort_id
    """
    try:
        data = request.get_json()
        driver_id = data.get('driver_id')
        escort_id = data.get('escort_id')
        
        if not driver_id or not escort_id:
            return jsonify({'error': 'Missing driver_id or escort_id'}), 400
        
        if not current_assignment_state['result']:
            return jsonify({'error': 'No active assignment. Please run assignment first.'}), 400
        
        drivers = current_assignment_state['drivers']
        passengers_data = current_assignment_state['passengers']
        drivers_data = current_assignment_state.get('drivers_data', [])
        
        # Get escort info
        escort = next((e for e in ESCORTS_DATA if e.get('id') == escort_id), None)
        if not escort:
            return jsonify({'error': 'Escort not found'}), 400
        
        escort_name = escort.get('name', 'Escort')
        
        # Check if escort is already assigned to another driver
        for driver in drivers:
            if driver.escort_id == escort_id and driver.id != driver_id:
                return jsonify({'error': f'Escort {escort_name} is already assigned to another driver'}), 400
        
        result = assign_escort_to_driver(driver_id, escort_id, drivers, ESCORTS_DATA)
        
        if result['success']:
            # Update stored state
            current_assignment_state['drivers'] = drivers
            
            # Update mappings to include escort_name for this driver
            mappings = current_assignment_state.get('mappings', [])
            print(f"\n=== ESCORT ASSIGNMENT DEBUG ===")
            print(f"Driver ID: {driver_id}, Escort ID: {escort_id}, Escort Name: {escort_name}")
            print(f"Total mappings before update: {len(mappings)}")
            
            # Find the last passenger mapping for this driver and update escort_name
            driver_mappings = [m for m in mappings if m.get('driver_id') == driver_id]
            print(f"Driver {driver_id} has {len(driver_mappings)} passenger mappings")
            
            if driver_mappings:
                # Sort by sequence_order to find the last one
                driver_mappings.sort(key=lambda x: x.get('sequence_order', 0))
                last_sequence = driver_mappings[-1].get('sequence_order', 0)
                print(f"Last sequence_order for driver {driver_id}: {last_sequence}")
                
                # Update escort_name and escort_id in the last mapping
                updated = False
                for i, mapping in enumerate(mappings):
                    if (mapping.get('driver_id') == driver_id and 
                        mapping.get('sequence_order') == last_sequence):
                        old_escort = mappings[i].get('escort_name', '0')
                        old_escort_id = mappings[i].get('escort_id')
                        mappings[i]['escort_name'] = escort_name
                        mappings[i]['escort_id'] = escort_id
                        updated = True
                        print(f"✓ UPDATED mapping {i}: driver_id={driver_id}, passenger_id={mapping.get('passenger_id')}, sequence={last_sequence}")
                        print(f"  Escort name: '{old_escort}' → '{escort_name}'")
                        print(f"  Escort ID: {old_escort_id} → {escort_id}")
                        break
                
                if not updated:
                    print(f"✗ ERROR: Could not find mapping to update!")
                    print(f"  Looking for: driver_id={driver_id}, sequence_order={last_sequence}")
                    print(f"  Available mappings for this driver:")
                    for m in driver_mappings:
                        print(f"    - passenger_id={m.get('passenger_id')}, sequence={m.get('sequence_order')}, escort={m.get('escort_name', '0')}")
            else:
                print(f"✗ ERROR: No mappings found for driver {driver_id}")
            
            current_assignment_state['mappings'] = mappings
            print(f"=== END DEBUG ===\n")
            
            return jsonify({
                'success': True,
                'message': result['message'],
                'escort_name': escort_name,
                'mappings_updated': True
            })
        else:
            return jsonify(result), 400
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Run the Flask development server on port 8080 to avoid permission issues
    app.run(debug=True, host='0.0.0.0', port=8080)
