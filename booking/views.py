# booking/views.py
"""
API views for the Aperture Booking.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib.auth import login
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from datetime import timedelta
from django.core.paginator import Paginator
from django.contrib.auth.models import User
from .models import UserProfile, Resource, Booking, ApprovalRule, Maintenance, EmailVerificationToken, PasswordResetToken, BookingTemplate, Notification, NotificationPreference, WaitingListEntry, Faculty, College, Department, ResourceAccess, AccessRequest, TrainingRequest
from .forms import UserRegistrationForm, UserProfileForm, CustomPasswordResetForm, CustomSetPasswordForm, BookingForm, RecurringBookingForm, BookingTemplateForm, CreateBookingFromTemplateForm, SaveAsTemplateForm
from .recurring import RecurringBookingGenerator, RecurringBookingManager
from .conflicts import ConflictDetector, ConflictResolver, ConflictManager
from .serializers import (
    UserProfileSerializer, ResourceSerializer, BookingSerializer,
    ApprovalRuleSerializer, MaintenanceSerializer, WaitingListEntrySerializer
)
# from .notifications import notification_service  # TODO: Implement notification service
# from .waiting_list import waiting_list_service  # TODO: Implement waiting list service  
# from .checkin_service import checkin_service  # TODO: Implement checkin service


class IsOwnerOrManagerPermission(permissions.BasePermission):
    """Custom permission to only allow owners or managers to edit bookings."""
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only to owner or lab managers
        if hasattr(request.user, 'userprofile'):
            user_profile = request.user.userprofile
            return (obj.user == request.user or 
                   user_profile.role in ['technician', 'sysadmin'])
        
        return obj.user == request.user


class IsManagerPermission(permissions.BasePermission):
    """Custom permission for managers only."""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        if hasattr(request.user, 'userprofile'):
            user_profile = request.user.userprofile
            return user_profile.role in ['technician', 'sysadmin']
        
        return False


class UserProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for user profiles."""
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter queryset based on user role."""
        user = self.request.user
        try:
            user_profile = user.userprofile
            if user_profile.role in ['technician', 'sysadmin']:
                return UserProfile.objects.all()
            else:
                # Regular users can only see their own profile and group members
                return UserProfile.objects.filter(
                    Q(user=user) | Q(group=user_profile.group)
                )
        except UserProfile.DoesNotExist:
            return UserProfile.objects.filter(user=user)


class ResourceViewSet(viewsets.ModelViewSet):
    """ViewSet for resources."""
    queryset = Resource.objects.filter(is_active=True)
    serializer_class = ResourceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['resource_type', 'requires_induction', 'required_training_level']
    
    def get_permissions(self):
        """Different permissions for different actions."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Only technicians and sysadmins can modify resources
            self.permission_classes = [permissions.IsAuthenticated, IsManagerPermission]
        return super().get_permissions()
    
    def get_queryset(self):
        """Filter resources based on query parameters."""
        queryset = super().get_queryset()
        
        # Filter by resource_type if provided
        resource_type = self.request.query_params.get('resource_type')
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
            
        return queryset
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        """Get resources available for the current user."""
        try:
            user_profile = request.user.userprofile
            available_resources = []
            
            for resource in self.get_queryset():
                if resource.is_available_for_user(user_profile):
                    available_resources.append(resource)
            
            serializer = self.get_serializer(available_resources, many=True)
            return Response(serializer.data)
        
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User profile not found"}, 
                status=status.HTTP_400_BAD_REQUEST
            )


class BookingViewSet(viewsets.ModelViewSet):
    """ViewSet for bookings with full CRUD operations."""
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrManagerPermission]
    
    def get_queryset(self):
        """Filter bookings based on user role and query parameters."""
        user = self.request.user
        queryset = Booking.objects.select_related('resource', 'user', 'approved_by')
        
        try:
            user_profile = user.userprofile
            
            # Filter by user role
            if user_profile.role in ['technician', 'sysadmin']:
                # Managers can see all bookings
                pass
            elif user_profile.role == 'lecturer':
                # Lecturers can see their bookings and their group's bookings
                queryset = queryset.filter(
                    Q(user=user) | 
                    Q(user__userprofile__group=user_profile.group, shared_with_group=True)
                )
            else:
                # Students/researchers see their own bookings and shared group bookings
                queryset = queryset.filter(
                    Q(user=user) |
                    Q(user__userprofile__group=user_profile.group, shared_with_group=True) |
                    Q(attendees=user)
                ).distinct()
        
        except UserProfile.DoesNotExist:
            queryset = queryset.filter(user=user)
        
        # Filter by query parameters
        resource_id = self.request.query_params.get('resource')
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(
                start_time__gte=start_date,
                end_time__lte=end_date
            )
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('start_time')
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a booking."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if booking.status != 'pending':
            return Response(
                {"error": "Only pending bookings can be approved"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'approved'
        booking.approved_by = request.user
        booking.approved_at = timezone.now()
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a booking."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if booking.status != 'pending':
            return Response(
                {"error": "Only pending bookings can be rejected"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'rejected'
        booking.approved_by = request.user
        booking.approved_at = timezone.now()
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a booking."""
        booking = self.get_object()
        
        if not booking.can_be_cancelled:
            return Response(
                {"error": "This booking cannot be cancelled"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'cancelled'
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """Get bookings in calendar event format."""
        queryset = self.get_queryset()
        
        # Convert to FullCalendar event format
        events = []
        for booking in queryset:
            color = {
                'pending': '#ffc107',
                'approved': '#28a745',
                'rejected': '#dc3545',
                'cancelled': '#6c757d',
                'completed': '#17a2b8'
            }.get(booking.status, '#007bff')
            
            events.append({
                'id': booking.id,
                'title': booking.title,
                'start': booking.start_time.isoformat(),
                'end': booking.end_time.isoformat(),
                'backgroundColor': color,
                'borderColor': color,
                'extendedProps': {
                    'resource': booking.resource.name,
                    'user': booking.user.get_full_name(),
                    'status': booking.status,
                    'description': booking.description,
                }
            })
        
        return Response(events)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get booking statistics."""
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Date range for statistics
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        bookings = Booking.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        stats = {
            'total_bookings': bookings.count(),
            'approved_bookings': bookings.filter(status='approved').count(),
            'pending_bookings': bookings.filter(status='pending').count(),
            'rejected_bookings': bookings.filter(status='rejected').count(),
            'cancelled_bookings': bookings.filter(status='cancelled').count(),
            'bookings_by_resource': list(
                bookings.values('resource__name')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
            'bookings_by_user': list(
                bookings.values('user__username', 'user__first_name', 'user__last_name')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
            'bookings_by_group': list(
                bookings.values('user__userprofile__group')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
        }
        
        return Response(stats)
    
    def destroy(self, request, *args, **kwargs):
        """Override destroy to cancel booking instead of deleting it."""
        booking = self.get_object()
        
        # Check if booking can be cancelled
        if not booking.can_be_cancelled:
            return Response(
                {"error": "This booking cannot be cancelled"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark as cancelled instead of deleting
        booking.status = 'cancelled'
        booking.save()
        
        # Create booking history entry
        from .models import BookingHistory
        BookingHistory.objects.create(
            booking=booking,
            user=request.user,
            action='cancelled',
            notes='Cancelled via API'
        )
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def add_prerequisite(self, request, pk=None):
        """Add a prerequisite booking dependency."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        # Check permissions - only owner or managers can add dependencies
        if booking.user != request.user and user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        prerequisite_id = request.data.get('prerequisite_id')
        dependency_type = request.data.get('dependency_type', 'sequential')
        conditions = request.data.get('conditions', {})
        
        if not prerequisite_id:
            return Response(
                {"error": "prerequisite_id is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            prerequisite_booking = Booking.objects.get(id=prerequisite_id)
            
            # Validate that user has access to prerequisite booking
            if (prerequisite_booking.user != request.user and 
                user_profile.role not in ['technician', 'sysadmin']):
                return Response(
                    {"error": "You don't have access to the specified prerequisite booking"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            booking.add_prerequisite(prerequisite_booking, dependency_type, conditions)
            
            serializer = self.get_serializer(booking)
            return Response(serializer.data)
            
        except Booking.DoesNotExist:
            return Response(
                {"error": "Prerequisite booking not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def remove_prerequisite(self, request, pk=None):
        """Remove a prerequisite booking dependency."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        # Check permissions
        if booking.user != request.user and user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        prerequisite_id = request.data.get('prerequisite_id')
        
        if not prerequisite_id:
            return Response(
                {"error": "prerequisite_id is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            prerequisite_booking = Booking.objects.get(id=prerequisite_id)
            booking.prerequisite_bookings.remove(prerequisite_booking)
            
            serializer = self.get_serializer(booking)
            return Response(serializer.data)
            
        except Booking.DoesNotExist:
            return Response(
                {"error": "Prerequisite booking not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def dependencies(self, request, pk=None):
        """Get booking dependency information."""
        booking = self.get_object()
        
        prerequisites = []
        for prereq in booking.prerequisite_bookings.all():
            prerequisites.append({
                'id': prereq.id,
                'title': prereq.title,
                'resource': prereq.resource.name,
                'start_time': prereq.start_time,
                'end_time': prereq.end_time,
                'status': prereq.status,
                'user': prereq.user.get_full_name()
            })
        
        dependents = []
        for dependent in booking.dependent_bookings.all():
            dependents.append({
                'id': dependent.id,
                'title': dependent.title,
                'resource': dependent.resource.name,
                'start_time': dependent.start_time,
                'end_time': dependent.end_time,
                'status': dependent.status,
                'user': dependent.user.get_full_name(),
                'dependency_type': dependent.dependency_type
            })
        
        return Response({
            'can_start': booking.can_start,
            'dependency_status': booking.dependency_status,
            'dependency_type': booking.dependency_type,
            'dependency_conditions': booking.dependency_conditions,
            'prerequisites': prerequisites,
            'dependents': dependents,
            'blocking_dependencies': [
                {
                    'id': dep.id,
                    'title': dep.title,
                    'status': dep.status,
                    'resource': dep.resource.name
                }
                for dep in booking.get_blocking_dependencies()
            ]
        })
    
    @action(detail=False, methods=['post'])
    def join_waiting_list(self, request):
        """Join waiting list when booking conflicts exist."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # Check if validation failed due to conflicts
            errors = serializer.errors
            if any('conflict' in str(error).lower() for error in errors.values()):
                # Offer to join waiting list
                resource_id = request.data.get('resource_id')
                start_time = request.data.get('start_time')
                end_time = request.data.get('end_time')
                title = request.data.get('title', 'Booking Request')
                description = request.data.get('description', '')
                
                if resource_id and start_time and end_time:
                    waiting_entry = WaitingListEntry.objects.create(
                        user=request.user,
                        resource_id=resource_id,
                        desired_start_time=start_time,
                        desired_end_time=end_time,
                        title=title,
                        description=description,
                        flexible_start=request.data.get('flexible_start', False),
                        flexible_duration=request.data.get('flexible_duration', False),
                        auto_book=request.data.get('auto_book', False)
                    )
                    
                    return Response({
                        'booking_failed': True,
                        'reason': 'time_conflict',
                        'waiting_list_entry': WaitingListEntrySerializer(waiting_entry).data,
                        'message': 'Booking conflicts detected. You have been added to the waiting list.'
                    }, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # If no conflicts, create booking normally
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class ApprovalRuleViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for approval rules (read-only for now)."""
    queryset = ApprovalRule.objects.filter(is_active=True)
    serializer_class = ApprovalRuleSerializer
    permission_classes = [permissions.IsAuthenticated]


class MaintenanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for maintenance schedules."""
    queryset = Maintenance.objects.all()
    serializer_class = MaintenanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter maintenance by date range if provided."""
        queryset = super().get_queryset()
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date and end_date:
            queryset = queryset.filter(
                start_time__gte=start_date,
                end_time__lte=end_date
            )
        
        return queryset.order_by('start_time')


# Template views
def register_view(request):
    """User registration view."""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request, 
                'Registration successful! Please check your email to verify your account before logging in.'
            )
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'registration/register.html', {'form': form})


def verify_email_view(request, token):
    """Email verification view."""
    verification_token = get_object_or_404(EmailVerificationToken, token=token)
    
    if verification_token.is_used:
        messages.warning(request, 'This verification link has already been used.')
        return redirect('login')
    
    if verification_token.is_expired():
        messages.error(request, 'This verification link has expired. Please contact support.')
        return redirect('login')
    
    # Activate user and mark email as verified
    user = verification_token.user
    user.is_active = True
    user.save()
    
    profile = user.userprofile
    profile.email_verified = True
    profile.save()
    
    verification_token.is_used = True
    verification_token.save()
    
    messages.success(request, 'Email verified successfully! You can now log in.')
    return redirect('login')


def resend_verification_view(request):
    """Resend verification email view."""
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            from django.contrib.auth.models import User
            user = User.objects.get(email=email, is_active=False)
            
            # Check if there's an existing unused token
            try:
                token = EmailVerificationToken.objects.get(user=user, is_used=False)
                if token.is_expired():
                    token.delete()
                    token = EmailVerificationToken.objects.create(user=user)
            except EmailVerificationToken.DoesNotExist:
                token = EmailVerificationToken.objects.create(user=user)
            
            # Send verification email
            form = UserRegistrationForm()
            form.send_verification_email(user, token)
            
            messages.success(request, 'Verification email has been resent. Please check your inbox.')
            
        except User.DoesNotExist:
            messages.error(request, 'No unverified account found with this email address.')
    
    return render(request, 'registration/resend_verification.html')


class CustomPasswordResetView(PasswordResetView):
    """Custom password reset view using our token system."""
    form_class = CustomPasswordResetForm
    template_name = 'registration/password_reset_form.html'
    success_url = '/password-reset-done/'
    
    def form_valid(self, form):
        form.save(request=self.request)
        return redirect(self.success_url)


def password_reset_confirm_view(request, token):
    """Custom password reset confirmation view."""
    reset_token = get_object_or_404(PasswordResetToken, token=token)
    
    if reset_token.is_used:
        messages.error(request, 'This password reset link has already been used.')
        return render(request, 'registration/password_reset_confirm.html', {'validlink': False})
    
    if reset_token.is_expired():
        messages.error(request, 'This password reset link has expired.')
        return render(request, 'registration/password_reset_confirm.html', {'validlink': False})
    
    if request.method == 'POST':
        form = CustomSetPasswordForm(reset_token.user, request.POST)
        if form.is_valid():
            form.save()
            reset_token.is_used = True
            reset_token.save()
            messages.success(request, 'Your password has been set successfully.')
            return redirect('password_reset_complete')
    else:
        form = CustomSetPasswordForm(reset_token.user)
    
    return render(request, 'registration/password_reset_confirm.html', {
        'form': form,
        'validlink': True,
    })


def password_reset_done_view(request):
    """Password reset done view."""
    return render(request, 'registration/password_reset_done.html')


def password_reset_complete_view(request):
    """Password reset complete view."""
    return render(request, 'registration/password_reset_complete.html')


@login_required
def create_booking_view(request):
    """Create a new booking."""
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                booking = form.save(commit=False)
                booking.user = request.user
                booking.save()
                
                messages.success(request, f'Booking "{booking.title}" created successfully.')
                return redirect('booking:booking_detail', pk=booking.pk)
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            # Add more detailed error messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = BookingForm(user=request.user)
    
    return render(request, 'booking/create_booking.html', {'form': form})


@login_required
def booking_detail_view(request, pk):
    """View booking details."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin'] and
            not booking.shared_with_group):
            messages.error(request, 'You do not have permission to view this booking.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        if booking.user != request.user:
            messages.error(request, 'You do not have permission to view this booking.')
            return redirect('booking:dashboard')
    
    # Handle POST requests (e.g., cancellation)
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'cancel':
            # Check if user can cancel this booking
            if (booking.user == request.user or 
                (hasattr(request.user, 'userprofile') and 
                 request.user.userprofile.role in ['technician', 'sysadmin'])):
                
                if booking.can_be_cancelled:
                    booking.status = 'cancelled'
                    booking.save()
                    messages.success(request, f'Booking "{booking.title}" has been cancelled.')
                    return redirect('booking:dashboard')
                else:
                    messages.error(request, 'This booking cannot be cancelled.')
            else:
                messages.error(request, 'You do not have permission to cancel this booking.')
    
    # Get recurring series if applicable
    recurring_series = None
    if booking.is_recurring:
        try:
            recurring_series = RecurringBookingManager.get_recurring_series(booking)
        except:
            recurring_series = None
    
    return render(request, 'booking/booking_detail.html', {
        'booking': booking,
        'recurring_series': recurring_series,
    })


@login_required
def create_recurring_booking_view(request, booking_pk):
    """Create recurring bookings based on an existing booking."""
    base_booking = get_object_or_404(Booking, pk=booking_pk, user=request.user)
    
    # Check if user can create recurring bookings
    try:
        user_profile = request.user.userprofile
        if not user_profile.can_create_recurring:
            messages.error(request, 'You do not have permission to create recurring bookings.')
            return redirect('booking:booking_detail', pk=booking_pk)
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to create recurring bookings.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        form = RecurringBookingForm(request.POST)
        if form.is_valid():
            try:
                pattern = form.create_pattern()
                generator = RecurringBookingGenerator(base_booking, pattern)
                
                skip_conflicts = form.cleaned_data.get('skip_conflicts', True)
                result = generator.create_recurring_bookings(skip_conflicts=skip_conflicts)
                
                # Update the base booking to mark it as recurring
                base_booking.is_recurring = True
                base_booking.recurring_pattern = pattern.to_dict()
                base_booking.save()
                
                success_msg = f"Created {result['total_created']} recurring bookings."
                if result['skipped_dates']:
                    success_msg += f" Skipped {len(result['skipped_dates'])} dates due to conflicts."
                
                messages.success(request, success_msg)
                return redirect('booking:booking_detail', pk=booking_pk)
                
            except Exception as e:
                messages.error(request, f'Error creating recurring bookings: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = RecurringBookingForm()
    
    return render(request, 'booking/create_recurring.html', {
        'form': form,
        'base_booking': base_booking,
    })


@login_required
def cancel_recurring_series_view(request, booking_pk):
    """Cancel an entire recurring series."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin']):
            messages.error(request, 'You do not have permission to cancel this booking series.')
            return redirect('booking:booking_detail', pk=booking_pk)
    except UserProfile.DoesNotExist:
        if booking.user != request.user:
            messages.error(request, 'You do not have permission to cancel this booking series.')
            return redirect('booking:booking_detail', pk=booking_pk)
    
    if not booking.is_recurring:
        messages.error(request, 'This is not a recurring booking.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        cancel_future_only = request.POST.get('cancel_future_only') == 'on'
        
        try:
            cancelled_count = RecurringBookingManager.cancel_recurring_series(
                booking, cancel_future_only=cancel_future_only
            )
            
            if cancel_future_only:
                messages.success(request, f'Cancelled {cancelled_count} future bookings in the series.')
            else:
                messages.success(request, f'Cancelled {cancelled_count} bookings in the entire series.')
                
            return redirect('booking:dashboard')
            
        except Exception as e:
            messages.error(request, f'Error cancelling recurring series: {str(e)}')
    
    # Get series info for confirmation
    series = RecurringBookingManager.get_recurring_series(booking)
    future_count = sum(1 for b in series if b.start_time > timezone.now() and b.can_be_cancelled)
    total_count = sum(1 for b in series if b.can_be_cancelled)
    
    return render(request, 'booking/cancel_recurring.html', {
        'booking': booking,
        'series': series,
        'future_count': future_count,
        'total_count': total_count,
    })


@login_required
def conflict_detection_view(request):
    """Conflict detection and resolution interface."""
    # Check if user has permission to view conflicts
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to access conflict management.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to access conflict management.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    resource_id = request.GET.get('resource')
    days_ahead = int(request.GET.get('days', 30))
    
    conflicts_data = {}
    selected_resource = None
    
    if resource_id:
        try:
            selected_resource = Resource.objects.get(pk=resource_id)
            conflicts_data = ConflictManager.get_resource_conflicts_report(
                selected_resource, days_ahead
            )
        except Resource.DoesNotExist:
            messages.error(request, 'Selected resource not found.')
    
    # Get all resources for filter dropdown
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'booking/conflicts.html', {
        'conflicts_data': conflicts_data,
        'selected_resource': selected_resource,
        'resources': resources,
        'days_ahead': days_ahead,
    })


@login_required
def resolve_conflict_view(request, conflict_type, id1, id2):
    """Resolve a specific conflict between two bookings."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to resolve conflicts.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to resolve conflicts.')
        return redirect('booking:dashboard')
    
    try:
        booking1 = Booking.objects.get(pk=id1)
        booking2 = Booking.objects.get(pk=id2)
    except Booking.DoesNotExist:
        messages.error(request, 'One or more bookings not found.')
        return redirect('booking:conflicts')
    
    # Verify there's actually a conflict
    conflicts = ConflictDetector.check_booking_conflicts(booking1, exclude_booking_ids=[])
    conflict = None
    for c in conflicts:
        if c.booking2.pk == booking2.pk:
            conflict = c
            break
    
    if not conflict:
        messages.warning(request, 'No conflict detected between these bookings.')
        return redirect('booking:conflicts')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'cancel_booking1':
            if booking1.can_be_cancelled:
                booking1.status = 'cancelled'
                booking1.save()
                messages.success(request, f'Cancelled booking: {booking1.title}')
            else:
                messages.error(request, f'Cannot cancel booking: {booking1.title}')
                
        elif action == 'cancel_booking2':
            if booking2.can_be_cancelled:
                booking2.status = 'cancelled'
                booking2.save()
                messages.success(request, f'Cancelled booking: {booking2.title}')
            else:
                messages.error(request, f'Cannot cancel booking: {booking2.title}')
                
        elif action == 'reschedule_booking1':
            new_start = request.POST.get('new_start_time')
            new_end = request.POST.get('new_end_time')
            if new_start and new_end:
                try:
                    booking1.start_time = timezone.datetime.fromisoformat(new_start.replace('T', ' '))
                    booking1.end_time = timezone.datetime.fromisoformat(new_end.replace('T', ' '))
                    booking1.save()
                    messages.success(request, f'Rescheduled booking: {booking1.title}')
                except Exception as e:
                    messages.error(request, f'Error rescheduling booking: {str(e)}')
            else:
                messages.error(request, 'Invalid time values provided.')
                
        elif action == 'reschedule_booking2':
            new_start = request.POST.get('new_start_time')
            new_end = request.POST.get('new_end_time')
            if new_start and new_end:
                try:
                    booking2.start_time = timezone.datetime.fromisoformat(new_start.replace('T', ' '))
                    booking2.end_time = timezone.datetime.fromisoformat(new_end.replace('T', ' '))
                    booking2.save()
                    messages.success(request, f'Rescheduled booking: {booking2.title}')
                except Exception as e:
                    messages.error(request, f'Error rescheduling booking: {str(e)}')
            else:
                messages.error(request, 'Invalid time values provided.')
        
        return redirect('booking:conflicts')
    
    # Generate suggestions for resolution
    try:
        user1_profile = booking1.user.userprofile
        user2_profile = booking2.user.userprofile
        
        suggestions1 = ConflictResolver.suggest_alternative_times(booking1, [conflict])
        suggestions2 = ConflictResolver.suggest_alternative_times(booking2, [conflict])
        
        alt_resources1 = ConflictResolver.suggest_alternative_resources(booking1, user1_profile)
        alt_resources2 = ConflictResolver.suggest_alternative_resources(booking2, user2_profile)
    except:
        suggestions1 = suggestions2 = []
        alt_resources1 = alt_resources2 = []
    
    return render(request, 'booking/resolve_conflict.html', {
        'conflict': conflict,
        'booking1': booking1,
        'booking2': booking2,
        'suggestions1': suggestions1,
        'suggestions2': suggestions2,
        'alt_resources1': alt_resources1,
        'alt_resources2': alt_resources2,
    })


@login_required 
def bulk_resolve_conflicts_view(request):
    """Bulk resolve multiple conflicts."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to resolve conflicts.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to resolve conflicts.')
        return redirect('booking:dashboard')
    
    if request.method == 'POST':
        resource_id = request.POST.get('resource_id')
        strategy = request.POST.get('strategy', 'suggest_alternatives')
        conflict_ids = request.POST.getlist('conflict_ids')
        
        try:
            resource = Resource.objects.get(pk=resource_id)
            
            # Get conflicts for the resource
            conflicts_data = ConflictManager.get_resource_conflicts_report(resource, 30)
            all_conflicts = []
            
            # Convert conflict data back to conflict objects for processing
            for conflict_dict in conflicts_data['all_conflicts']:
                try:
                    booking1 = Booking.objects.get(pk=conflict_dict['booking1']['id'])
                    booking2 = Booking.objects.get(pk=conflict_dict['booking2']['id'])
                    from .conflicts import BookingConflict
                    conflict_obj = BookingConflict(booking1, booking2)
                    all_conflicts.append(conflict_obj)
                except Booking.DoesNotExist:
                    continue
            
            # Filter to selected conflicts if specified
            if conflict_ids:
                selected_conflicts = []
                for conflict in all_conflicts:
                    conflict_id = f"{conflict.booking1.pk}_{conflict.booking2.pk}"
                    if conflict_id in conflict_ids:
                        selected_conflicts.append(conflict)
                all_conflicts = selected_conflicts
            
            # Bulk resolve
            if all_conflicts:
                resolution_results = ConflictManager.bulk_resolve_conflicts(
                    all_conflicts, strategy
                )
                
                messages.success(
                    request, 
                    f"Processed {len(all_conflicts)} conflicts. "
                    f"{resolution_results['summary']['auto_resolvable']} can be auto-resolved, "
                    f"{resolution_results['summary']['manual_review']} need manual review."
                )
            else:
                messages.warning(request, 'No conflicts selected for resolution.')
                
        except Resource.DoesNotExist:
            messages.error(request, 'Resource not found.')
        except Exception as e:
            messages.error(request, f'Error processing conflicts: {str(e)}')
    
    return redirect('booking:conflicts')


@login_required
def notifications_list(request):
    """Display user's notifications."""
    notifications = notification_service.get_user_notifications(
        request.user, 
        limit=50, 
        unread_only=False
    )
    
    unread_count = len([n for n in notifications if n.status in ['pending', 'sent']])
    
    return render(request, 'booking/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def notification_preferences(request):
    """Display and update user's notification preferences."""
    if request.method == 'POST':
        # Update preferences
        for key, value in request.POST.items():
            if key.startswith('pref_'):
                # Parse preference key: pref_{notification_type}_{delivery_method}
                parts = key.replace('pref_', '').split('_')
                if len(parts) >= 2:
                    notification_type = '_'.join(parts[:-1])
                    delivery_method = parts[-1]
                    
                    preference, created = NotificationPreference.objects.get_or_create(
                        user=request.user,
                        notification_type=notification_type,
                        delivery_method=delivery_method,
                        defaults={'is_enabled': value == 'on'}
                    )
                    
                    if not created:
                        preference.is_enabled = value == 'on'
                        preference.save()
        
        messages.success(request, 'Notification preferences updated successfully.')
        return redirect('booking:notification_preferences')
    
    # Get current preferences
    preferences = {}
    user_prefs = NotificationPreference.objects.filter(user=request.user)
    
    for pref in user_prefs:
        key = f"{pref.notification_type}_{pref.delivery_method}"
        preferences[key] = pref.is_enabled
    
    # Available notification types and delivery methods
    notification_types = NotificationPreference.NOTIFICATION_TYPES
    delivery_methods = NotificationPreference.DELIVERY_METHODS
    
    return render(request, 'booking/notification_preferences.html', {
        'preferences': preferences,
        'notification_types': notification_types,
        'delivery_methods': delivery_methods,
    })


# API Views for notifications
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for user notifications."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user,
            delivery_method='in_app'
        ).select_related('booking', 'resource', 'maintenance').order_by('-created_at')
    
    def get_serializer_class(self):
        # Simple serializer for notifications
        from rest_framework import serializers
        
        class NotificationSerializer(serializers.ModelSerializer):
            class Meta:
                model = Notification
                fields = [
                    'id', 'notification_type', 'title', 'message', 'priority',
                    'status', 'created_at', 'sent_at', 'read_at', 'metadata'
                ]
                read_only_fields = fields
        
        return NotificationSerializer
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = self.get_queryset().filter(status__in=['pending', 'sent']).count()
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read."""
        notification_ids = list(
            self.get_queryset().filter(status__in=['pending', 'sent']).values_list('id', flat=True)
        )
        
        updated_count = notification_service.mark_notifications_as_read(
            request.user, notification_ids
        )
        
        return Response({
            'marked_read': updated_count,
            'message': f'Marked {updated_count} notifications as read'
        })
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a specific notification as read."""
        notification = self.get_object()
        notification.mark_as_read()
        
        return Response({
            'status': 'read',
            'message': 'Notification marked as read'
        })


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """API viewset for notification preferences."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        from rest_framework import serializers
        
        class NotificationPreferenceSerializer(serializers.ModelSerializer):
            class Meta:
                model = NotificationPreference
                fields = [
                    'id', 'notification_type', 'delivery_method', 
                    'is_enabled', 'frequency', 'created_at', 'updated_at'
                ]
                read_only_fields = ['id', 'created_at', 'updated_at']
        
        return NotificationPreferenceSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# Waiting List Views
@login_required
def waiting_list_view(request):
    """Display user's waiting list entries."""
    entries = waiting_list_service.get_user_waiting_list_entries(request.user)
    
    # Get pending notifications
    notifications = WaitingListNotification.objects.filter(
        waiting_list_entry__user=request.user,
        user_response='pending'
    ).select_related('waiting_list_entry__resource').order_by('-sent_at')
    
    return render(request, 'booking/waiting_list.html', {
        'waiting_list_entries': entries,
        'pending_notifications': notifications,
    })


@login_required
def join_waiting_list(request, resource_id):
    """Join waiting list for a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if user can access this resource
    try:
        user_profile = request.user.userprofile
        if not resource.is_available_for_user(user_profile):
            messages.error(request, f'You do not meet the requirements to book {resource.name}.')
            return redirect('booking:calendar')
    except:
        messages.error(request, 'User profile not found.')
        return redirect('booking:calendar')
    
    if request.method == 'POST':
        try:
            # Get form data
            preferred_start = timezone.datetime.fromisoformat(request.POST['preferred_start_time'])
            preferred_end = timezone.datetime.fromisoformat(request.POST['preferred_end_time'])
            
            # Optional parameters
            options = {
                'min_duration_minutes': int(request.POST.get('min_duration_minutes', 60)),
                'max_duration_minutes': int(request.POST.get('max_duration_minutes', 240)),
                'flexible_start_time': request.POST.get('flexible_start_time') == 'on',
                'flexible_duration': request.POST.get('flexible_duration') == 'on',
                'auto_book': request.POST.get('auto_book') == 'on',
                'priority': request.POST.get('priority', 'normal'),
                'notes': request.POST.get('notes', ''),
            }
            
            # Add to waiting list
            entry = waiting_list_service.add_to_waiting_list(
                user=request.user,
                resource=resource,
                preferred_start=preferred_start,
                preferred_end=preferred_end,
                **options
            )
            
            messages.success(request, f'Successfully added to waiting list for {resource.name}!')
            return redirect('booking:waiting_list')
            
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Failed to join waiting list: {str(e)}')
    
    # Pre-fill with requested time if available
    requested_start = request.GET.get('start_time')
    requested_end = request.GET.get('end_time')
    
    return render(request, 'booking/join_waiting_list.html', {
        'resource': resource,
        'requested_start_time': requested_start,
        'requested_end_time': requested_end,
    })


@login_required
def leave_waiting_list(request, entry_id):
    """Leave waiting list."""
    success, message = waiting_list_service.cancel_waiting_list_entry(entry_id, request.user)
    
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    
    return redirect('booking:waiting_list')


@login_required
def respond_to_availability(request, notification_id):
    """Respond to availability notification."""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'accept':
            success, message = waiting_list_service.accept_availability_offer(notification_id, request.user)
        elif action == 'decline':
            success, message = waiting_list_service.decline_availability_offer(notification_id, request.user)
        else:
            success, message = False, 'Invalid action.'
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
    
    return redirect('booking:waiting_list')


# API Views for Waiting List
class WaitingListEntryViewSet(viewsets.ModelViewSet):
    """API viewset for waiting list entries."""
    serializer_class = WaitingListEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get waiting list entries based on user permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return WaitingListEntry.objects.all().select_related('user', 'resource', 'resulting_booking')
        else:
            return WaitingListEntry.objects.filter(user=self.request.user).select_related('resource', 'resulting_booking')
    
    def perform_create(self, serializer):
        """Create waiting list entry for current user."""
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel waiting list entry."""
        entry = self.get_object()
        
        if entry.user != request.user and request.user.userprofile.role not in ['technician', 'sysadmin']:
            return Response({'error': 'Permission denied'}, status=403)
        
        if entry.status not in ['waiting', 'notified']:
            return Response({'error': 'Cannot cancel entry in current status'}, status=400)
        
        entry.cancel_waiting()
        return Response({'status': 'success', 'message': 'Waiting list entry cancelled'})
    
    @action(detail=True, methods=['post'])
    def book_slot(self, request, pk=None):
        """Book an available slot from waiting list entry."""
        entry = self.get_object()
        
        if entry.user != request.user:
            return Response({'error': 'Permission denied'}, status=403)
        
        if entry.status != 'notified':
            return Response({'error': 'No available slot to book'}, status=400)
        
        # Get slot details from request
        slot_data = request.data.get('slot')
        if not slot_data:
            return Response({'error': 'Slot data required'}, status=400)
        
        try:
            booking = entry.create_booking_from_slot(slot_data)
            return Response({
                'status': 'success',
                'message': 'Booking created successfully',
                'booking_id': booking.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=400)
    
    @action(detail=False, methods=['get'])
    def find_opportunities(self, request):
        """Find available booking opportunities for waiting list entries."""
        if request.user.userprofile.role not in ['technician', 'sysadmin']:
            return Response({'error': 'Permission denied'}, status=403)
        
        resource_id = request.query_params.get('resource')
        resource = None
        
        if resource_id:
            try:
                resource = Resource.objects.get(id=resource_id)
            except Resource.DoesNotExist:
                return Response({'error': 'Resource not found'}, status=404)
        
        opportunities = WaitingListEntry.find_opportunities(resource)
        
        # Format the response
        formatted_opportunities = []
        for opportunity in opportunities:
            entry_data = WaitingListEntrySerializer(opportunity['entry']).data
            formatted_opportunities.append({
                'entry': entry_data,
                'available_slots': opportunity['slots']
            })
        
        return Response(formatted_opportunities)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get waiting list statistics."""
        if request.user.userprofile.role not in ['technician', 'sysadmin']:
            return Response({'error': 'Permission denied'}, status=403)
        
        resource_id = request.query_params.get('resource')
        queryset = self.get_queryset()
        
        if resource_id:
            try:
                resource = Resource.objects.get(id=resource_id)
                queryset = queryset.filter(resource=resource)
            except Resource.DoesNotExist:
                return Response({'error': 'Resource not found'}, status=404)
        
        # Calculate statistics
        stats = {
            'total_entries': queryset.count(),
            'waiting': queryset.filter(status='waiting').count(),
            'notified': queryset.filter(status='notified').count(),
            'booked': queryset.filter(status='booked').count(),
            'expired': queryset.filter(status='expired').count(),
            'cancelled': queryset.filter(status='cancelled').count(),
            'by_priority': {
                'urgent': queryset.filter(priority='urgent').count(),
                'high': queryset.filter(priority='high').count(),
                'normal': queryset.filter(priority='normal').count(),
                'low': queryset.filter(priority='low').count(),
            },
            'auto_book_enabled': queryset.filter(auto_book=True).count()
        }
        
        return Response(stats)


# WaitingListNotificationViewSet removed - using Notification model instead


@login_required
def resources_list_view(request):
    """View to display all available resources with access control."""
    resources = Resource.objects.filter(is_active=True).order_by('resource_type', 'name')
    
    # Add access information for each resource
    for resource in resources:
        resource.user_has_access_result = resource.user_has_access(request.user)
        resource.can_view_calendar_result = resource.can_user_view_calendar(request.user)
        
        # Check if user has pending access request
        resource.has_pending_request = AccessRequest.objects.filter(
            resource=resource,
            user=request.user,
            status='pending'
        ).exists()
        
        # Check if user has pending training request
        resource.has_pending_training = TrainingRequest.objects.filter(
            resource=resource,
            user=request.user,
            status__in=['pending', 'scheduled']
        ).exists()
    
    return render(request, 'booking/resources_list.html', {
        'resources': resources,
        'user': request.user,
    })


@login_required
def resource_detail_view(request, resource_id):
    """View to show resource details and calendar or access request form."""
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    
    # Check user's access
    user_has_access = resource.user_has_access(request.user)
    can_view_calendar = resource.can_user_view_calendar(request.user)
    
    # Check if user has pending access request
    has_pending_request = AccessRequest.objects.filter(
        resource=resource,
        user=request.user,
        status='pending'
    ).exists()
    
    # Check if user has pending training request
    has_pending_training = TrainingRequest.objects.filter(
        resource=resource,
        user=request.user,
        status__in=['pending', 'scheduled']
    ).exists()
    
    # If user can view calendar, show calendar view
    if can_view_calendar:
        return render(request, 'booking/resource_detail.html', {
            'resource': resource,
            'user_has_access': user_has_access,
            'can_view_calendar': can_view_calendar,
            'has_pending_training': has_pending_training,
            'show_calendar': True,
        })
    
    # Otherwise show access request form
    return render(request, 'booking/resource_detail.html', {
        'resource': resource,
        'user_has_access': user_has_access,
        'can_view_calendar': can_view_calendar,
        'has_pending_request': has_pending_request,
        'has_pending_training': has_pending_training,
        'show_calendar': False,
    })


@login_required
def request_resource_access_view(request, resource_id):
    """Handle resource access requests."""
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    
    # Check if user already has access or pending request
    if resource.user_has_access(request.user):
        messages.info(request, 'You already have access to this resource.')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    if AccessRequest.objects.filter(resource=resource, user=request.user, status='pending').exists():
        messages.info(request, 'You already have a pending access request for this resource.')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    # Check if user has pending training request
    if TrainingRequest.objects.filter(resource=resource, user=request.user, status__in=['pending', 'scheduled']).exists():
        messages.info(request, 'You already have a pending training request for this resource.')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    if request.method == 'POST':
        access_type = request.POST.get('access_type', 'book')
        justification = request.POST.get('justification', '').strip()
        requested_duration_days = request.POST.get('requested_duration_days')
        has_training = request.POST.get('has_training', '')
        
        if not justification:
            messages.error(request, 'Please provide a justification for your access request.')
            return redirect('booking:request_resource_access', resource_id=resource.id)
        
        # Check if user meets training requirements
        user_profile = request.user.userprofile
        needs_training = resource.required_training_level > user_profile.training_level
        
        if needs_training:
            if has_training == 'yes':
                # User claims to have training but system shows they don't
                messages.warning(request, 
                    f'Our records show you have training level {user_profile.training_level}, but {resource.name} requires level {resource.required_training_level}. '
                    'Training information will be sent to you to update your qualifications.')
                
                # Create training request for verification
                training_request, created = TrainingRequest.objects.get_or_create(
                    user=request.user,
                    resource=resource,
                    status__in=['pending', 'scheduled'],
                    defaults={
                        'requested_level': resource.required_training_level,
                        'current_level': user_profile.training_level,
                        'justification': f"Training verification needed for access to {resource.name}. User claims training completion. Original request: {justification}",
                        'status': 'pending'
                    }
                )
                
            elif has_training == 'no':
                # User acknowledges they need training
                messages.info(request, 'Training information will be sent to you as this resource requires additional training.')
                
                # Create training request
                training_request, created = TrainingRequest.objects.get_or_create(
                    user=request.user,
                    resource=resource,
                    status__in=['pending', 'scheduled'],
                    defaults={
                        'requested_level': resource.required_training_level,
                        'current_level': user_profile.training_level,
                        'justification': f"Training needed for access to {resource.name}. Original request: {justification}",
                        'status': 'pending'
                    }
                )
            
            if 'training_request' in locals():
                if created:
                    messages.success(request, f'Training request for {resource.name} has been submitted. You will be contacted with training details.')
                    
                    # Send notifications
                    try:
                        from .notifications import training_request_notifications
                        training_request_notifications.training_request_submitted(training_request)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Failed to send training request submission notification: {e}")
                else:
                    messages.info(request, f'You already have a pending training request for {resource.name}.')
            
            return redirect('booking:resource_detail', resource_id=resource.id)
        
        # User has sufficient training, proceed with access request
        access_request = AccessRequest.objects.create(
            resource=resource,
            user=request.user,
            access_type=access_type,
            justification=justification,
            requested_duration_days=int(requested_duration_days) if requested_duration_days else None
        )
        
        messages.success(request, f'Access request for {resource.name} has been submitted successfully.')
        
        # Send notifications
        try:
            from .notifications import access_request_notifications
            access_request_notifications.access_request_submitted(access_request)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send access request submission notification: {e}")
        
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    return render(request, 'booking/request_access.html', {
        'resource': resource,
    })


@login_required
def notification_preferences_view(request):
    """Notification preferences management view."""
    from .models import NotificationPreference
    
    # Get all notification types
    notification_types = NotificationPreference.NOTIFICATION_TYPES
    delivery_methods = NotificationPreference.DELIVERY_METHODS
    frequency_choices = [
        ('immediate', 'Immediate'),
        ('daily_digest', 'Daily Digest'),
        ('weekly_digest', 'Weekly Digest'),
    ]
    
    if request.method == 'POST':
        # Process preference updates
        updated_count = 0
        
        for notification_type, _ in notification_types:
            for delivery_method, _ in delivery_methods:
                # Get form field names
                enabled_field = f"{notification_type}_{delivery_method}_enabled"
                frequency_field = f"{notification_type}_{delivery_method}_frequency"
                
                is_enabled = request.POST.get(enabled_field) == 'on'
                frequency = request.POST.get(frequency_field, 'immediate')
                
                # Update or create preference
                preference, created = NotificationPreference.objects.update_or_create(
                    user=request.user,
                    notification_type=notification_type,
                    delivery_method=delivery_method,
                    defaults={
                        'is_enabled': is_enabled,
                        'frequency': frequency
                    }
                )
                
                if created or preference.is_enabled != is_enabled:
                    updated_count += 1
        
        messages.success(request, f'Updated {updated_count} notification preferences.')
        return redirect('booking:notification_preferences')
    
    # Get current preferences
    current_preferences = {}
    user_prefs = NotificationPreference.objects.filter(user=request.user)
    
    for pref in user_prefs:
        key = f"{pref.notification_type}_{pref.delivery_method}"
        current_preferences[key] = {
            'enabled': pref.is_enabled,
            'frequency': pref.frequency
        }
    
    # Add default values for missing preferences
    from .notifications import notification_service
    for notification_type, _ in notification_types:
        for delivery_method, _ in delivery_methods:
            key = f"{notification_type}_{delivery_method}"
            if key not in current_preferences:
                defaults = notification_service.default_preferences.get(notification_type, {})
                current_preferences[key] = {
                    'enabled': defaults.get(delivery_method, False),
                    'frequency': defaults.get('frequency', 'immediate')
                }
    
    return render(request, 'booking/notification_preferences.html', {
        'notification_types': notification_types,
        'delivery_methods': delivery_methods,
        'frequency_choices': frequency_choices,
        'current_preferences': current_preferences,
    })


@login_required
def profile_view(request):
    """User profile management view."""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile, current_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserProfileForm(instance=profile, current_user=request.user)
    
    return render(request, 'registration/profile.html', {'form': form, 'profile': profile})


@login_required
def calendar_view(request):
    """Main calendar view."""
    return render(request, 'booking/calendar.html', {
        'user': request.user,
        'resources': Resource.objects.filter(is_active=True),
    })


@login_required
def dashboard_view(request):
    """User dashboard view."""
    user_bookings = Booking.objects.filter(user=request.user).order_by('-created_at')[:10]
    return render(request, 'booking/dashboard.html', {
        'user': request.user,
        'recent_bookings': user_bookings,
    })


@login_required
def template_list_view(request):
    """List user's booking templates."""
    # Get templates accessible to the user
    accessible_templates = []
    for template in BookingTemplate.objects.all():
        if template.is_accessible_by_user(request.user):
            accessible_templates.append(template.pk)
    
    templates = BookingTemplate.objects.filter(
        pk__in=accessible_templates
    ).order_by('-use_count', 'name')
    
    user_templates = templates.filter(user=request.user)
    public_templates = templates.filter(is_public=True).exclude(user=request.user)
    group_templates = templates.exclude(user=request.user, is_public=True)
    
    return render(request, 'booking/templates.html', {
        'user_templates': user_templates,
        'public_templates': public_templates,
        'group_templates': group_templates,
    })


@login_required
def template_create_view(request):
    """Create a new booking template."""
    if request.method == 'POST':
        form = BookingTemplateForm(request.POST, user=request.user)
        if form.is_valid():
            template = form.save(commit=False)
            template.user = request.user
            template.save()
            messages.success(request, f'Template "{template.name}" created successfully.')
            return redirect('booking:templates')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookingTemplateForm(user=request.user)
    
    return render(request, 'booking/template_form.html', {
        'form': form,
        'title': 'Create Template',
    })


@login_required
def template_edit_view(request, pk):
    """Edit a booking template."""
    template = get_object_or_404(BookingTemplate, pk=pk)
    
    # Check if user can edit this template
    if template.user != request.user:
        messages.error(request, 'You can only edit your own templates.')
        return redirect('booking:templates')
    
    if request.method == 'POST':
        form = BookingTemplateForm(request.POST, instance=template, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Template "{template.name}" updated successfully.')
            return redirect('booking:templates')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookingTemplateForm(instance=template, user=request.user)
    
    return render(request, 'booking/template_form.html', {
        'form': form,
        'template': template,
        'title': 'Edit Template',
    })


@login_required
def template_delete_view(request, pk):
    """Delete a booking template."""
    template = get_object_or_404(BookingTemplate, pk=pk)
    
    # Check if user can delete this template
    if template.user != request.user:
        messages.error(request, 'You can only delete your own templates.')
        return redirect('booking:templates')
    
    if request.method == 'POST':
        template_name = template.name
        template.delete()
        messages.success(request, f'Template "{template_name}" deleted successfully.')
        return redirect('booking:templates')
    
    return render(request, 'booking/template_confirm_delete.html', {
        'template': template,
    })


@login_required
def create_booking_from_template_view(request):
    """Create a booking from a template."""
    if request.method == 'POST':
        form = CreateBookingFromTemplateForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                booking = form.create_booking()
                booking.save()
                messages.success(request, f'Booking "{booking.title}" created from template.')
                return redirect('booking:booking_detail', pk=booking.pk)
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CreateBookingFromTemplateForm(user=request.user)
    
    return render(request, 'booking/create_from_template.html', {
        'form': form,
    })


@login_required
def save_booking_as_template_view(request, booking_pk):
    """Save an existing booking as a template."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    
    # Check if user owns the booking
    if booking.user != request.user:
        messages.error(request, 'You can only save your own bookings as templates.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        form = SaveAsTemplateForm(request.POST)
        if form.is_valid():
            try:
                template = booking.save_as_template(
                    template_name=form.cleaned_data['name'],
                    template_description=form.cleaned_data['description'],
                    is_public=form.cleaned_data['is_public']
                )
                messages.success(request, f'Booking saved as template "{template.name}".')
                return redirect('booking:templates')
            except Exception as e:
                messages.error(request, f'Error saving template: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Pre-fill form with booking data
        initial_data = {
            'name': f"{booking.title} Template",
            'description': f"Template based on booking: {booking.title}",
        }
        form = SaveAsTemplateForm(initial=initial_data)
    
    return render(request, 'booking/save_as_template.html', {
        'form': form,
        'booking': booking,
    })


@login_required
def bulk_booking_operations_view(request):
    """Bulk operations on multiple bookings."""
    if request.method == 'POST':
        action = request.POST.get('action')
        booking_ids = request.POST.getlist('booking_ids')
        
        if not booking_ids:
            messages.error(request, 'No bookings selected.')
            return redirect('booking:dashboard')
        
        try:
            user_profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            messages.error(request, 'User profile not found.')
            return redirect('booking:dashboard')
        
        # Get bookings that user has permission to modify
        if user_profile.role in ['technician', 'sysadmin']:
            bookings = Booking.objects.filter(pk__in=booking_ids)
        else:
            bookings = Booking.objects.filter(pk__in=booking_ids, user=request.user)
        
        if not bookings.exists():
            messages.error(request, 'No bookings found or you do not have permission to modify them.')
            return redirect('booking:dashboard')
        
        success_count = 0
        error_count = 0
        errors = []
        
        if action == 'cancel':
            for booking in bookings:
                if booking.can_be_cancelled:
                    booking.status = 'cancelled'
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Cannot be cancelled')
            
            if success_count > 0:
                messages.success(request, f'Successfully cancelled {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be cancelled: {", ".join(errors[:3])}')
        
        elif action == 'approve' and user_profile.role in ['technician', 'sysadmin']:
            for booking in bookings:
                if booking.status == 'pending':
                    booking.status = 'approved'
                    booking.approved_by = request.user
                    booking.approved_at = timezone.now()
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Not pending')
            
            if success_count > 0:
                messages.success(request, f'Successfully approved {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be approved: {", ".join(errors[:3])}')
        
        elif action == 'reject' and user_profile.role in ['technician', 'sysadmin']:
            for booking in bookings:
                if booking.status == 'pending':
                    booking.status = 'rejected'
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Not pending')
            
            if success_count > 0:
                messages.success(request, f'Successfully rejected {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be rejected: {", ".join(errors[:3])}')
        
        else:
            messages.error(request, 'Invalid action or insufficient permissions.')
    
    return redirect('booking:dashboard')


@login_required
def booking_management_view(request):
    """Management interface for bookings with bulk operations."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to access booking management.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to access booking management.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    resource_filter = request.GET.get('resource', '')
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Base queryset
    bookings = Booking.objects.select_related('resource', 'user', 'approved_by').order_by('-created_at')
    
    # Apply filters
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    
    if resource_filter:
        bookings = bookings.filter(resource_id=resource_filter)
    
    if user_filter:
        bookings = bookings.filter(
            Q(user__username__icontains=user_filter) |
            Q(user__first_name__icontains=user_filter) |
            Q(user__last_name__icontains=user_filter)
        )
    
    if date_from:
        try:
            from_date = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__gte=from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__lte=to_date)
        except ValueError:
            pass
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(bookings, 25)  # Show 25 bookings per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources for filter dropdown
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'resources': resources,
        'status_filter': status_filter,
        'resource_filter': resource_filter,
        'user_filter': user_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Booking.STATUS_CHOICES,
    }
    
    return render(request, 'booking/booking_management.html', context)


@login_required
def my_bookings_view(request):
    """User's own bookings with bulk operations."""
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    resource_filter = request.GET.get('resource', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Base queryset - user's own bookings
    bookings = Booking.objects.filter(user=request.user).select_related('resource', 'approved_by').order_by('-created_at')
    
    # Apply filters
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    
    if resource_filter:
        bookings = bookings.filter(resource_id=resource_filter)
    
    if date_from:
        try:
            from_date = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__gte=from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__lte=to_date)
        except ValueError:
            pass
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(bookings, 20)  # Show 20 bookings per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources for filter dropdown (only ones user has access to)
    try:
        user_profile = request.user.userprofile
        available_resources = []
        for resource in Resource.objects.filter(is_active=True):
            if resource.is_available_for_user(user_profile):
                available_resources.append(resource.pk)
        resources = Resource.objects.filter(pk__in=available_resources).order_by('name')
    except:
        resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'resources': resources,
        'status_filter': status_filter,
        'resource_filter': resource_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Booking.STATUS_CHOICES,
    }
    
    return render(request, 'booking/my_bookings.html', context)


@login_required
def edit_booking_view(request, pk):
    """Edit an existing booking."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        can_edit = (booking.user == request.user or 
                   user_profile.role in ['technician', 'sysadmin'])
    except UserProfile.DoesNotExist:
        can_edit = booking.user == request.user
    
    if not can_edit:
        messages.error(request, 'You do not have permission to edit this booking.')
        return redirect('booking:booking_detail', pk=pk)
    
    # Check if booking can be edited
    if booking.status not in ['pending', 'approved']:
        messages.error(request, 'Only pending or approved bookings can be edited.')
        return redirect('booking:booking_detail', pk=pk)
    
    # Don't allow editing past bookings
    if booking.start_time < timezone.now():
        messages.error(request, 'Cannot edit bookings that have already started.')
        return redirect('booking:booking_detail', pk=pk)
    
    if request.method == 'POST':
        form = BookingForm(request.POST, instance=booking, user=request.user)
        if form.is_valid():
            try:
                updated_booking = form.save(commit=False)
                
                # If the booking was approved and user made changes, set it back to pending
                if (booking.status == 'approved' and 
                    booking.user == request.user and 
                    user_profile.role not in ['technician', 'sysadmin']):
                    
                    # Check if any important fields changed
                    important_changes = (
                        updated_booking.resource != booking.resource or
                        updated_booking.start_time != booking.start_time or
                        updated_booking.end_time != booking.end_time
                    )
                    
                    if important_changes:
                        updated_booking.status = 'pending'
                        updated_booking.approved_by = None
                        updated_booking.approved_at = None
                        messages.info(request, 'Booking updated and set to pending approval due to time/resource changes.')
                    else:
                        messages.success(request, 'Booking updated successfully.')
                else:
                    messages.success(request, 'Booking updated successfully.')
                
                updated_booking.save()
                return redirect('booking:booking_detail', pk=updated_booking.pk)
                
            except Exception as e:
                messages.error(request, f'Error updating booking: {str(e)}')
        else:
            # Add detailed error messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = BookingForm(instance=booking, user=request.user)
    
    return render(request, 'booking/edit_booking.html', {
        'form': form,
        'booking': booking,
    })


@login_required
def cancel_booking_view(request, pk):
    """Cancel a booking with confirmation."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        can_cancel = (booking.user == request.user or 
                     user_profile.role in ['technician', 'sysadmin'])
    except UserProfile.DoesNotExist:
        can_cancel = booking.user == request.user
    
    if not can_cancel:
        messages.error(request, 'You do not have permission to cancel this booking.')
        return redirect('booking:booking_detail', pk=pk)
    
    if not booking.can_be_cancelled:
        messages.error(request, 'This booking cannot be cancelled.')
        return redirect('booking:booking_detail', pk=pk)
    
    if request.method == 'POST':
        confirm = request.POST.get('confirm')
        if confirm == 'yes':
            booking.status = 'cancelled'
            booking.save()
            messages.success(request, f'Booking "{booking.title}" has been cancelled.')
            
            # Redirect based on user role
            if hasattr(request.user, 'userprofile') and request.user.userprofile.role in ['technician', 'sysadmin']:
                return redirect('booking:manage_bookings')
            else:
                return redirect('booking:my_bookings')
        else:
            return redirect('booking:booking_detail', pk=pk)
    
    return render(request, 'booking/cancel_booking.html', {
        'booking': booking,
    })


@login_required
def duplicate_booking_view(request, pk):
    """Create a new booking based on an existing one."""
    original_booking = get_object_or_404(Booking, pk=pk)
    
    # Check if user has access to view the original booking
    try:
        user_profile = request.user.userprofile
        can_access = (
            original_booking.user == request.user or 
            user_profile.role in ['technician', 'sysadmin'] or
            (original_booking.shared_with_group and 
             user_profile.group == original_booking.user.userprofile.group)
        )
    except UserProfile.DoesNotExist:
        can_access = original_booking.user == request.user
    
    if not can_access:
        messages.error(request, 'You do not have permission to duplicate this booking.')
        return redirect('booking:dashboard')
    
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                new_booking = form.save(commit=False)
                new_booking.user = request.user
                new_booking.status = 'pending'
                new_booking.save()
                
                messages.success(request, f'Booking "{new_booking.title}" created successfully.')
                return redirect('booking:booking_detail', pk=new_booking.pk)
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            # Add detailed error messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        # Pre-populate form with original booking data, but adjust times
        initial_data = {
            'resource': original_booking.resource,
            'title': f"Copy of {original_booking.title}",
            'description': original_booking.description,
            'shared_with_group': original_booking.shared_with_group,
            'notes': original_booking.notes,
        }
        
        # Set start time to tomorrow at the same time
        tomorrow = timezone.now() + timedelta(days=1)
        duration = original_booking.end_time - original_booking.start_time
        
        start_time = tomorrow.replace(
            hour=original_booking.start_time.hour,
            minute=original_booking.start_time.minute,
            second=0,
            microsecond=0
        )
        end_time = start_time + duration
        
        initial_data['start_time'] = start_time
        initial_data['end_time'] = end_time
        
        form = BookingForm(initial=initial_data, user=request.user)
    
    return render(request, 'booking/duplicate_booking.html', {
        'form': form,
        'original_booking': original_booking,
    })


# Check-in/Check-out Views
@login_required
def checkin_view(request, booking_id):
    """Check in to a booking."""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Check if user can check in
    try:
        user_profile = request.user.userprofile
        can_checkin = (
            booking.user == request.user or
            booking.attendees.filter(id=request.user.id).exists() or
            user_profile.role in ['technician', 'sysadmin']
        )
    except UserProfile.DoesNotExist:
        can_checkin = booking.user == request.user
    
    if not can_checkin:
        messages.error(request, 'You do not have permission to check in to this booking.')
        return redirect('booking:booking_detail', pk=booking_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        # Get client info for tracking
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        success, message = checkin_service.check_in_booking(
            booking_id=booking_id,
            user=request.user,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('booking:booking_detail', pk=booking_id)
    
    return render(request, 'booking/checkin.html', {
        'booking': booking,
    })


@login_required
def checkout_view(request, booking_id):
    """Check out of a booking."""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Check if user can check out
    try:
        user_profile = request.user.userprofile
        can_checkout = (
            booking.user == request.user or
            booking.attendees.filter(id=request.user.id).exists() or
            user_profile.role in ['technician', 'sysadmin']
        )
    except UserProfile.DoesNotExist:
        can_checkout = booking.user == request.user
    
    if not can_checkout:
        messages.error(request, 'You do not have permission to check out of this booking.')
        return redirect('booking:booking_detail', pk=booking_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        # Get client info for tracking
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        success, message = checkin_service.check_out_booking(
            booking_id=booking_id,
            user=request.user,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('booking:booking_detail', pk=booking_id)
    
    return render(request, 'booking/checkout.html', {
        'booking': booking,
    })


@login_required
def checkin_status_view(request):
    """View current check-in status for user's bookings."""
    # Get user's bookings for today
    today = timezone.now().date()
    user_bookings = Booking.objects.filter(
        Q(user=request.user) | Q(attendees=request.user),
        start_time__date=today,
        status__in=['approved', 'confirmed']
    ).select_related('resource').distinct().order_by('start_time')
    
    # Get currently checked in bookings
    checked_in_bookings = Booking.objects.filter(
        Q(user=request.user) | Q(attendees=request.user),
        checked_in_at__isnull=False,
        checked_out_at__isnull=True
    ).select_related('resource').distinct()
    
    return render(request, 'booking/checkin_status.html', {
        'user_bookings': user_bookings,
        'checked_in_bookings': checked_in_bookings,
        'today': today,
    })


@login_required
def resource_checkin_status_view(request, resource_id):
    """View current check-in status for a specific resource (managers only)."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if user has permission
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view resource check-in status.')
            return redirect('booking:calendar')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view resource check-in status.')
        return redirect('booking:calendar')
    
    # Get current check-ins for this resource
    current_checkins = checkin_service.get_current_checkins(resource)
    
    # Get today's bookings for this resource
    today = timezone.now().date()
    today_bookings = Booking.objects.filter(
        resource=resource,
        start_time__date=today,
        status__in=['approved', 'confirmed']
    ).select_related('user').order_by('start_time')
    
    # Get overdue check-ins and check-outs for this resource
    overdue_checkins = [b for b in checkin_service.get_overdue_checkins() if b.resource == resource]
    overdue_checkouts = [b for b in checkin_service.get_overdue_checkouts() if b.resource == resource]
    
    return render(request, 'booking/resource_checkin_status.html', {
        'resource': resource,
        'current_checkins': current_checkins,
        'today_bookings': today_bookings,
        'overdue_checkins': overdue_checkins,
        'overdue_checkouts': overdue_checkouts,
        'today': today,
    })


@login_required
def usage_analytics_view(request):
    """View usage analytics (managers only)."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view usage analytics.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view usage analytics.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    resource_id = request.GET.get('resource')
    days = int(request.GET.get('days', 30))
    
    # Calculate date range
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    # Get analytics
    resource = None
    if resource_id:
        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            pass
    
    analytics = checkin_service.get_usage_analytics(
        resource=resource,
        start_date=start_date,
        end_date=end_date
    )
    
    # Get all resources for filter
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'booking/usage_analytics.html', {
        'analytics': analytics,
        'resource': resource,
        'resources': resources,
        'days': days,
        'start_date': start_date,
        'end_date': end_date,
    })


# API Views for Check-in/Check-out
@login_required
def api_checkin_booking(request, booking_id):
    """API endpoint for checking in to a booking."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    success, message = checkin_service.check_in_booking(
        booking_id=booking_id,
        user=request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    if success:
        return JsonResponse({'success': True, 'message': message})
    else:
        return JsonResponse({'success': False, 'message': message}, status=400)


@login_required  
def api_checkout_booking(request, booking_id):
    """API endpoint for checking out of a booking."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    success, message = checkin_service.check_out_booking(
        booking_id=booking_id,
        user=request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    if success:
        return JsonResponse({'success': True, 'message': message})
    else:
        return JsonResponse({'success': False, 'message': message}, status=400)


def ajax_load_colleges(request):
    """AJAX view to load colleges based on faculty selection."""
    faculty_id = request.GET.get('faculty_id')
    colleges = College.objects.filter(faculty_id=faculty_id, is_active=True).order_by('name')
    data = [{'id': college.id, 'name': college.name} for college in colleges]
    return JsonResponse({'colleges': data})


def ajax_load_departments(request):
    """AJAX view to load departments based on college selection."""
    college_id = request.GET.get('college_id')
    departments = Department.objects.filter(college_id=college_id, is_active=True).order_by('name')
    data = [{'id': department.id, 'name': department.name} for department in departments]
    return JsonResponse({'departments': data})


@login_required
def group_management_view(request):
    """Group management interface for managers."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to manage groups.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to manage groups.')
        return redirect('booking:dashboard')

    # Handle POST requests for group operations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_group':
            return handle_create_group(request)
        elif action == 'rename_group':
            return handle_rename_group(request)
        elif action == 'merge_groups':
            return handle_merge_groups(request)
        elif action == 'delete_group':
            return handle_delete_group(request)
        elif action == 'bulk_assign':
            return handle_bulk_assign_users(request)

    # Get groups with member counts
    groups_data = UserProfile.objects.exclude(group='').values('group').annotate(
        member_count=Count('id'),
        students=Count('id', filter=Q(role='student')),
        researchers=Count('id', filter=Q(role='researcher')),
        academics=Count('id', filter=Q(role='academic')),
        technicians=Count('id', filter=Q(role='technician')),
        recent_activity=Count('user__booking', filter=Q(user__booking__created_at__gte=timezone.now() - timedelta(days=30)))
    ).order_by('-member_count')

    # Get users without groups
    ungrouped_users = UserProfile.objects.filter(group='').select_related('user')
    
    # Get recent group activities (bookings by group members)
    recent_bookings = Booking.objects.filter(
        user__userprofile__group__isnull=False,
        created_at__gte=timezone.now() - timedelta(days=7)
    ).select_related('user__userprofile', 'resource').order_by('-created_at')[:20]

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        groups_data = groups_data.filter(group__icontains=search_query)

    # Pagination
    paginator = Paginator(groups_data, 20)
    page_number = request.GET.get('page')
    groups_page = paginator.get_page(page_number)

    context = {
        'groups_data': groups_page,
        'ungrouped_users': ungrouped_users,
        'recent_bookings': recent_bookings,
        'search_query': search_query,
        'total_groups': groups_data.count(),
        'total_ungrouped': ungrouped_users.count(),
    }

    return render(request, 'booking/group_management.html', context)


@login_required  
def group_detail_view(request, group_name):
    """Detailed view of a specific group."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view group details.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view group details.')
        return redirect('booking:dashboard')

    # Get group members
    group_members = UserProfile.objects.filter(group=group_name).select_related(
        'user', 'faculty', 'college', 'department'
    ).order_by('user__last_name', 'user__first_name')

    if not group_members.exists():
        messages.error(request, f'Group "{group_name}" not found.')
        return redirect('booking:group_management')

    # Handle POST requests for member management
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'remove_member':
            user_id = request.POST.get('user_id')
            try:
                member = UserProfile.objects.get(id=user_id, group=group_name)
                member.group = ''
                member.save()
                messages.success(request, f'Removed {member.user.get_full_name()} from group {group_name}.')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User not found in this group.')
        
        elif action == 'change_role':
            user_id = request.POST.get('user_id')
            new_role = request.POST.get('new_role')
            try:
                member = UserProfile.objects.get(id=user_id, group=group_name)
                member.role = new_role
                member.save()
                messages.success(request, f'Changed {member.user.get_full_name()}\'s role to {new_role}.')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User not found in this group.')
        
        return redirect('booking:group_detail', group_name=group_name)

    # Get group statistics
    group_stats = {
        'total_members': group_members.count(),
        'roles': group_members.values('role').annotate(count=Count('id')),
        'recent_bookings': Booking.objects.filter(
            user__userprofile__group=group_name,
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count(),
        'active_bookings': Booking.objects.filter(
            user__userprofile__group=group_name,
            status__in=['pending', 'approved'],
            start_time__gte=timezone.now()
        ).count(),
    }

    # Get group's recent bookings
    recent_bookings = Booking.objects.filter(
        user__userprofile__group=group_name
    ).select_related('user', 'resource').order_by('-created_at')[:10]

    # Available users to add to group
    available_users = UserProfile.objects.filter(group='').select_related('user')

    context = {
        'group_name': group_name,
        'group_members': group_members,
        'group_stats': group_stats,
        'recent_bookings': recent_bookings,
        'available_users': available_users,
        'role_choices': UserProfile.ROLE_CHOICES,
    }

    return render(request, 'booking/group_detail.html', context)


def handle_create_group(request):
    """Handle group creation."""
    group_name = request.POST.get('group_name', '').strip()
    description = request.POST.get('description', '').strip()
    
    if not group_name:
        messages.error(request, 'Group name is required.')
        return redirect('booking:group_management')
    
    # Check if group already exists
    if UserProfile.objects.filter(group=group_name).exists():
        messages.error(request, f'Group "{group_name}" already exists.')
        return redirect('booking:group_management')
    
    # For now, we'll just create the group when first user is assigned
    # In a more advanced implementation, we might have a separate Group model
    messages.success(request, f'Group "{group_name}" will be created when first user is assigned.')
    return redirect('booking:group_management')


def handle_rename_group(request):
    """Handle group renaming."""
    old_name = request.POST.get('old_group_name', '').strip()
    new_name = request.POST.get('new_group_name', '').strip()
    
    if not old_name or not new_name:
        messages.error(request, 'Both old and new group names are required.')
        return redirect('booking:group_management')
    
    if old_name == new_name:
        messages.error(request, 'New group name must be different from old name.')
        return redirect('booking:group_management')
    
    # Check if new name already exists
    if UserProfile.objects.filter(group=new_name).exists():
        messages.error(request, f'Group "{new_name}" already exists.')
        return redirect('booking:group_management')
    
    # Rename the group
    updated = UserProfile.objects.filter(group=old_name).update(group=new_name)
    
    if updated > 0:
        messages.success(request, f'Renamed group "{old_name}" to "{new_name}" for {updated} users.')
    else:
        messages.error(request, f'Group "{old_name}" not found.')
    
    return redirect('booking:group_management')


def handle_merge_groups(request):
    """Handle merging groups."""
    source_group = request.POST.get('source_group', '').strip()
    target_group = request.POST.get('target_group', '').strip()
    
    if not source_group or not target_group:
        messages.error(request, 'Both source and target group names are required.')
        return redirect('booking:group_management')
    
    if source_group == target_group:
        messages.error(request, 'Source and target groups must be different.')
        return redirect('booking:group_management')
    
    # Check if both groups exist
    source_count = UserProfile.objects.filter(group=source_group).count()
    target_count = UserProfile.objects.filter(group=target_group).count()
    
    if source_count == 0:
        messages.error(request, f'Source group "{source_group}" not found.')
        return redirect('booking:group_management')
    
    if target_count == 0:
        messages.error(request, f'Target group "{target_group}" not found.')
        return redirect('booking:group_management')
    
    # Merge the groups
    updated = UserProfile.objects.filter(group=source_group).update(group=target_group)
    
    messages.success(request, f'Merged {updated} users from "{source_group}" into "{target_group}".')
    return redirect('booking:group_management')


def handle_delete_group(request):
    """Handle group deletion (removes group assignment from users)."""
    group_name = request.POST.get('group_name', '').strip()
    
    if not group_name:
        messages.error(request, 'Group name is required.')
        return redirect('booking:group_management')
    
    # Remove group assignment from all users
    updated = UserProfile.objects.filter(group=group_name).update(group='')
    
    if updated > 0:
        messages.success(request, f'Removed group assignment from {updated} users in "{group_name}".')
    else:
        messages.error(request, f'Group "{group_name}" not found.')
    
    return redirect('booking:group_management')


def handle_bulk_assign_users(request):
    """Handle bulk assignment of users to a group."""
    group_name = request.POST.get('target_group', '').strip()
    user_ids = request.POST.getlist('user_ids')
    
    if not group_name:
        messages.error(request, 'Target group name is required.')
        return redirect('booking:group_management')
    
    if not user_ids:
        messages.error(request, 'No users selected.')
        return redirect('booking:group_management')
    
    # Update selected users
    updated = UserProfile.objects.filter(id__in=user_ids).update(group=group_name)
    
    messages.success(request, f'Assigned {updated} users to group "{group_name}".')
    return redirect('booking:group_management')


@login_required
def add_user_to_group(request, group_name):
    """Add a user to a specific group via AJAX."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    user_id = request.POST.get('user_id')
    
    try:
        user_profile = UserProfile.objects.get(id=user_id)
        user_profile.group = group_name
        user_profile.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Added {user_profile.user.get_full_name()} to group {group_name}.'
        })
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)