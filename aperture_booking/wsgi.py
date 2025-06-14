# aperture_booking/wsgi.py
"""
WSGI config for aperture_booking project.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aperture_booking.settings')

application = get_wsgi_application()