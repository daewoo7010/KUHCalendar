# Attendance Management System

This project is an Attendance Management System built using Django. It allows users to manage attendance, leave requests, and trip requests efficiently.

## Project Structure

The project consists of the following main components:

- **attendance_management/**: The main Django project directory containing configuration files.
  - `__init__.py`: Indicates that this directory should be treated as a Python package.
  - `asgi.py`: ASGI configuration for asynchronous server communication.
  - `settings.py`: Contains settings for the Django project, including database configurations and installed apps.
  - `urls.py`: Defines URL routing for the project, mapping URLs to views.
  - `wsgi.py`: WSGI configuration for communication with WSGI-compatible web servers.

- **attendance/**: The Django app for managing attendance-related functionalities.
  - `__init__.py`: Indicates that this directory should be treated as a Python package.
  - `admin.py`: Used to register models with the Django admin site.
  - `apps.py`: Contains configuration for the attendance app.
  - `migrations/`: Directory for database migrations.
    - `__init__.py`: Indicates that this directory should be treated as a Python package.
  - `models.py`: Defines the models for the attendance app, including `CustomUser`, `LeaveBalance`, `LeaveRequest`, and `TripRequest`.
  - `tests.py`: Used for writing tests for the attendance app.
  - `views.py`: Used for defining views for the attendance app.

- **manage.py**: Command-line utility for interacting with the Django project.

- **requirements.txt**: Lists the dependencies required for the project.

## Features

- User management with custom user model.
- Leave management including leave requests and balances.
- Trip request management.

## Installation

1. Clone the repository.
2. Navigate to the project directory.
3. Install the required packages using:

   ```
   pip install -r requirements.txt
   ```

4. Apply migrations:

   ```
   python manage.py migrate
   ```

5. Run the development server:

   ```
   python manage.py runserver
   ```

## Usage

Access the application at `http://127.0.0.1:8000/` in your web browser. Use the Django admin interface to manage users, leave requests, and trip requests.

## License

This project is licensed under the MIT License.