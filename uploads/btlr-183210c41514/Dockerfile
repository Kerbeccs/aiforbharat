FROM python:3.9-slim-buster

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt requirements.txt

# Install dependencies
RUN pip install -r requirements.txt

# Copy the application code
COPY..

# Expose port 5000
EXPOSE 5000

# Run the app
CMD ["python", "app.py"]