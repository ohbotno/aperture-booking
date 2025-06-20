# booking/admin.py
"""
Django admin configuration for the Aperture Booking.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperture-booking.org/commercial
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import (
    AboutPage, UserProfile, Resource, Booking, BookingAttendee, 
    ApprovalRule, Maintenance, BookingHistory,
    Notification, NotificationPreference, EmailTemplate, PushSubscription,
    WaitingListEntry,
    CheckInOutEvent, UsageAnalytics,
    Faculty, College, Department,
    ResourceAccess, AccessRequest, TrainingRequest,
    SystemSetting, PDFExportSettings,
    ResourceResponsible, RiskAssessment, UserRiskAssessment,
    TrainingCourse, ResourceTrainingRequirement, UserTraining,
    ApprovalStatistics, MaintenanceVendor, MaintenanceDocument,
    MaintenanceAlert, MaintenanceAnalytics, ResourceUtilizationTrend,
    ChecklistTemplate, ChecklistItem, ChecklistCompletion, ChecklistItemCompletion
)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(AboutPage)
class AboutPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'facility_name', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'facility_name', 'content')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'facility_name', 'is_active')
        }),
        ('Content', {
            'fields': ('content',),
            'description': 'Main content for the about page. HTML is allowed.'
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_phone', 'address', 'emergency_contact'),
            'classes': ('collapse',)
        }),
        ('Operational Information', {
            'fields': ('operating_hours', 'policies_url', 'safety_information'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_active and AboutPage.objects.filter(is_active=True).count() == 1:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('created_at',)


@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'faculty', 'is_active', 'created_at')
    list_filter = ('faculty', 'is_active')
    search_fields = ('name', 'code', 'faculty__name')
    readonly_fields = ('created_at',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'college', 'is_active', 'created_at')
    list_filter = ('college__faculty', 'college', 'is_active')
    search_fields = ('name', 'code', 'college__name', 'college__faculty__name')
    readonly_fields = ('created_at',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'academic_path', 'student_level', 'training_level', 'is_inducted')
    list_filter = ('role', 'faculty', 'college', 'department', 'student_level', 'training_level', 'is_inducted')
    search_fields = (
        'user__username', 'user__email', 'user__first_name', 'user__last_name', 
        'student_id', 'staff_number', 'faculty__name', 'college__name', 'department__name'
    )
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'role')
        }),
        ('Academic Structure', {
            'fields': ('faculty', 'college', 'department', 'group')
        }),
        ('Role-Specific Information', {
            'fields': ('student_id', 'student_level', 'staff_number')
        }),
        ('System Information', {
            'fields': ('training_level', 'is_inducted', 'email_verified', 'phone')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['export_users_csv', 'bulk_assign_group', 'bulk_change_role', 'bulk_set_training_level']
    
    def export_users_csv(self, request, queryset):
        """Export selected users to CSV format."""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'username', 'email', 'first_name', 'last_name', 'role', 'group',
            'faculty_code', 'college_code', 'department_code', 'student_id',
            'staff_number', 'training_level', 'phone'
        ])
        
        for profile in queryset.select_related('user', 'faculty', 'college', 'department'):
            writer.writerow([
                profile.user.username,
                profile.user.email,
                profile.user.first_name,
                profile.user.last_name,
                profile.role,
                profile.group,
                profile.faculty.code if profile.faculty else '',
                profile.college.code if profile.college else '',
                profile.department.code if profile.department else '',
                profile.student_id or '',
                profile.staff_number or '',
                profile.training_level,
                profile.phone,
            ])
        
        return response
    export_users_csv.short_description = 'Export selected users as CSV'
    
    def bulk_assign_group(self, request, queryset):
        """Bulk assign group to selected users."""
        # This could be expanded to show a form, for now we'll use a simple approach
        from django.contrib import messages
        
        group_name = request.POST.get('group_name', '').strip()
        if group_name:
            updated = queryset.update(group=group_name)
            messages.success(request, f'Assigned {updated} users to group "{group_name}"')
        else:
            messages.error(request, 'Please provide a group name')
    bulk_assign_group.short_description = 'Assign group to selected users'
    
    def bulk_change_role(self, request, queryset):
        """Bulk change role for selected users."""
        # This would benefit from a proper form interface
        pass
    bulk_change_role.short_description = 'Change role for selected users'
    
    def bulk_set_training_level(self, request, queryset):
        """Bulk set training level for selected users."""
        training_level = request.POST.get('training_level')
        if training_level and training_level.isdigit():
            level = int(training_level)
            if 1 <= level <= 5:
                updated = queryset.update(training_level=level)
                self.message_user(request, f'Set training level to {level} for {updated} users.')
            else:
                self.message_user(request, 'Training level must be between 1 and 5.', level='error')
        else:
            self.message_user(request, 'Please provide a valid training level (1-5).', level='error')
    bulk_set_training_level.short_description = 'Set training level for selected users'
    
    def changelist_view(self, request, extra_context=None):
        """Add CSV import functionality to the changelist view."""
        extra_context = extra_context or {}
        
        if request.method == 'POST' and 'csv_file' in request.FILES:
            return self.handle_csv_import(request)
        
        # Add groups summary for group management
        try:
            from django.db.models import Count
            groups_summary = UserProfile.objects.exclude(group='').values('group').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            extra_context['groups_summary'] = groups_summary
        except:
            pass
            
        return super().changelist_view(request, extra_context)
    
    def handle_csv_import(self, request):
        """Handle CSV file upload and import."""
        from django.contrib import messages
        from django.shortcuts import redirect
        import tempfile
        import os
        
        csv_file = request.FILES['csv_file']
        update_existing = request.POST.get('update_existing') == 'on'
        
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a CSV file.')
            return redirect('admin:booking_userprofile_changelist')
        
        try:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv') as tmp_file:
                for chunk in csv_file.chunks():
                    tmp_file.write(chunk)
                tmp_file_path = tmp_file.name
            
            # Import using management command logic
            from booking.management.commands.import_users_csv import Command
            command = Command()
            
            # Capture output
            from io import StringIO
            output = StringIO()
            command.stdout = output
            
            # Run import
            command.handle(
                csv_file=tmp_file_path,
                dry_run=False,
                update_existing=update_existing,
                default_password='ChangeMe123!'
            )
            
            # Clean up
            os.unlink(tmp_file_path)
            
            # Show results
            output_text = output.getvalue()
            if 'Error' in output_text:
                messages.warning(request, f'Import completed with some issues:\n{output_text}')
            else:
                messages.success(request, f'Import successful:\n{output_text}')
                
        except Exception as e:
            messages.error(request, f'Import failed: {str(e)}')
        
        return redirect('admin:booking_userprofile_changelist')


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'resource_type', 'location', 'capacity', 'required_training_level', 'is_active')
    list_filter = ('resource_type', 'location', 'is_active', 'requires_induction')
    search_fields = ('name', 'description', 'location')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('title', 'resource', 'user', 'start_time', 'end_time', 'status', 'checkin_status', 'is_checked_in')
    list_filter = ('status', 'resource__resource_type', 'is_recurring', 'shared_with_group', 'no_show', 'auto_checked_out')
    search_fields = ('title', 'description', 'user__username', 'resource__name')
    readonly_fields = ('created_at', 'updated_at', 'approved_at', 'checked_in_at', 'checked_out_at', 'actual_start_time', 'actual_end_time')
    date_hierarchy = 'start_time'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'resource', 'user', 'status')
        }),
        ('Scheduling', {
            'fields': ('start_time', 'end_time', 'is_recurring', 'recurring_pattern')
        }),
        ('Sharing & Attendees', {
            'fields': ('shared_with_group', 'notes')
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
        ('Check-in/Check-out', {
            'fields': ('checked_in_at', 'checked_out_at', 'actual_start_time', 'actual_end_time', 'no_show', 'auto_checked_out'),
            'classes': ('collapse',)
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['mark_no_show', 'auto_check_out_selected']
    
    def is_checked_in(self, obj):
        return obj.is_checked_in
    is_checked_in.boolean = True
    is_checked_in.short_description = 'Checked In'
    
    def checkin_status(self, obj):
        return obj.checkin_status
    checkin_status.short_description = 'Status'
    
    def mark_no_show(self, request, queryset):
        """Mark selected bookings as no-show."""
        from .checkin_service import checkin_service
        
        count = 0
        for booking in queryset:
            if not booking.checked_in_at and not booking.no_show:
                try:
                    success, message = checkin_service.mark_no_show(booking.id, request.user, "Marked by admin")
                    if success:
                        count += 1
                except Exception:
                    pass
        
        self.message_user(request, f'Marked {count} bookings as no-show.')
    mark_no_show.short_description = 'Mark selected bookings as no-show'
    
    def auto_check_out_selected(self, request, queryset):
        """Auto check-out selected bookings."""
        count = 0
        for booking in queryset:
            if booking.is_checked_in:
                try:
                    if booking.auto_check_out():
                        count += 1
                except Exception:
                    pass
        
        self.message_user(request, f'Auto checked-out {count} bookings.')
    auto_check_out_selected.short_description = 'Auto check-out selected bookings'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource', 'user', 'approved_by')


@admin.register(BookingAttendee)
class BookingAttendeeAdmin(admin.ModelAdmin):
    list_display = ('booking', 'user', 'is_primary', 'added_at')
    list_filter = ('is_primary',)
    search_fields = ('booking__title', 'user__username')


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'resource', 'approval_type', 'is_active', 'priority')
    list_filter = ('approval_type', 'is_active')
    search_fields = ('name', 'resource__name')
    filter_horizontal = ('approvers',)



@admin.register(BookingHistory)
class BookingHistoryAdmin(admin.ModelAdmin):
    list_display = ('booking', 'user', 'action', 'timestamp')
    list_filter = ('action',)
    search_fields = ('booking__title', 'user__username', 'action')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'delivery_method', 'status', 'priority', 'created_at', 'retry_count')
    list_filter = ('notification_type', 'delivery_method', 'status', 'priority', 'created_at')
    search_fields = ('title', 'message', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at', 'sent_at', 'read_at', 'next_retry_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Notification Details', {
            'fields': ('user', 'notification_type', 'title', 'message', 'priority', 'delivery_method', 'status')
        }),
        ('Related Objects', {
            'fields': ('booking', 'resource', 'maintenance', 'access_request', 'training_request'),
            'classes': ('collapse',)
        }),
        ('Delivery Information', {
            'fields': ('sent_at', 'read_at', 'retry_count', 'next_retry_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['mark_as_sent', 'mark_as_read', 'retry_failed', 'send_pending', 'delete_old_notifications']
    
    def mark_as_sent(self, request, queryset):
        """Mark selected notifications as sent."""
        count = 0
        for notification in queryset.filter(status__in=['pending', 'failed']):
            notification.mark_as_sent()
            count += 1
        self.message_user(request, f'Marked {count} notifications as sent.')
    mark_as_sent.short_description = 'Mark as sent'
    
    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read."""
        count = 0
        for notification in queryset.filter(status__in=['pending', 'sent']):
            notification.mark_as_read()
            count += 1
        self.message_user(request, f'Marked {count} notifications as read.')
    mark_as_read.short_description = 'Mark as read'
    
    def retry_failed(self, request, queryset):
        """Retry failed notifications."""
        from .notifications import notification_service
        
        failed_notifications = queryset.filter(status='failed')
        for notification in failed_notifications:
            notification.status = 'pending'
            notification.next_retry_at = None
            notification.save(update_fields=['status', 'next_retry_at'])
        
        sent_count = notification_service.send_pending_notifications()
        self.message_user(request, f'Reset {failed_notifications.count()} failed notifications. {sent_count} notifications processed.')
    retry_failed.short_description = 'Retry failed notifications'
    
    def send_pending(self, request, queryset):
        """Send pending notifications."""
        from .notifications import notification_service
        
        sent_count = notification_service.send_pending_notifications()
        self.message_user(request, f'Processed pending notifications. {sent_count} notifications sent.')
    send_pending.short_description = 'Send pending notifications'
    
    def delete_old_notifications(self, request, queryset):
        """Delete notifications older than 30 days."""
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=30)
        old_notifications = queryset.filter(created_at__lt=cutoff_date)
        count = old_notifications.count()
        old_notifications.delete()
        
        self.message_user(request, f'Deleted {count} notifications older than 30 days.')
    delete_old_notifications.short_description = 'Delete notifications older than 30 days'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'booking', 'resource', 'maintenance')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'delivery_method', 'is_enabled', 'frequency')
    list_filter = ('notification_type', 'delivery_method', 'is_enabled', 'frequency')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    
    actions = ['enable_notifications', 'disable_notifications', 'set_immediate_frequency', 'set_daily_digest']
    
    def enable_notifications(self, request, queryset):
        """Enable selected notification preferences."""
        updated = queryset.update(is_enabled=True)
        self.message_user(request, f'Enabled {updated} notification preferences.')
    enable_notifications.short_description = 'Enable selected preferences'
    
    def disable_notifications(self, request, queryset):
        """Disable selected notification preferences.""" 
        updated = queryset.update(is_enabled=False)
        self.message_user(request, f'Disabled {updated} notification preferences.')
    disable_notifications.short_description = 'Disable selected preferences'
    
    def set_immediate_frequency(self, request, queryset):
        """Set frequency to immediate for selected preferences."""
        updated = queryset.update(frequency='immediate')
        self.message_user(request, f'Set {updated} preferences to immediate frequency.')
    set_immediate_frequency.short_description = 'Set to immediate frequency'
    
    def set_daily_digest(self, request, queryset):
        """Set frequency to daily digest for selected preferences."""
        updated = queryset.update(frequency='daily_digest')
        self.message_user(request, f'Set {updated} preferences to daily digest.')
    set_daily_digest.short_description = 'Set to daily digest'


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'notification_type', 'is_active', 'created_at')
    list_filter = ('notification_type', 'is_active')
    search_fields = ('name', 'subject_template')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'notification_type', 'is_active')
        }),
        ('Email Content', {
            'fields': ('subject_template', 'html_template', 'text_template')
        }),
        ('Template Variables', {
            'fields': ('available_variables',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'endpoint_preview', 'user_agent', 'is_active', 'created_at', 'last_used')
    list_filter = ('is_active', 'created_at', 'last_used')
    search_fields = ('user__username', 'user__email', 'user_agent', 'endpoint')
    readonly_fields = ('created_at', 'last_used', 'endpoint', 'p256dh_key', 'auth_key')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'is_active')
        }),
        ('Subscription Details', {
            'fields': ('endpoint', 'p256dh_key', 'auth_key', 'user_agent')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_used'),
            'classes': ('collapse',)
        })
    )
    
    def endpoint_preview(self, obj):
        """Show preview of endpoint URL."""
        return f"{obj.endpoint[:60]}..." if len(obj.endpoint) > 60 else obj.endpoint
    endpoint_preview.short_description = 'Endpoint'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
    actions = ['activate_subscriptions', 'deactivate_subscriptions', 'cleanup_inactive', 'test_push_notification']
    
    def activate_subscriptions(self, request, queryset):
        """Activate selected push subscriptions."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Activated {updated} push subscriptions.')
    activate_subscriptions.short_description = 'Activate selected subscriptions'
    
    def deactivate_subscriptions(self, request, queryset):
        """Deactivate selected push subscriptions."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {updated} push subscriptions.')
    deactivate_subscriptions.short_description = 'Deactivate selected subscriptions'
    
    def cleanup_inactive(self, request, queryset):
        """Remove inactive push subscriptions."""
        from .push_service import push_service
        removed = push_service.cleanup_inactive_subscriptions(days_old=30)
        self.message_user(request, f'Removed {removed} inactive push subscriptions.')
    cleanup_inactive.short_description = 'Clean up inactive subscriptions (30+ days)'
    
    def test_push_notification(self, request, queryset):
        """Send test push notifications to selected subscriptions."""
        from .push_service import push_service
        
        sent_count = 0
        for subscription in queryset.filter(is_active=True):
            success = push_service.send_push_notification(
                subscription=subscription,
                title="Test Notification",
                message="This is a test push notification from the admin interface.",
                data={'test': True, 'source': 'admin'}
            )
            if success:
                sent_count += 1
        
        self.message_user(request, f'Sent test notifications to {sent_count} devices.')
    test_push_notification.short_description = 'Send test push notification'


@admin.register(WaitingListEntry)
class WaitingListEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'desired_start_time', 'status', 'priority', 'created_at')
    list_filter = ('status', 'priority', 'resource__resource_type', 'flexible_start', 'auto_book')
    search_fields = ('user__username', 'user__email', 'resource__name', 'title', 'description')
    readonly_fields = ('created_at', 'updated_at', 'position', 'times_notified', 'last_notification_sent')
    date_hierarchy = 'desired_start_time'
    
    fieldsets = (
        ('User and Resource', {
            'fields': ('user', 'resource', 'status', 'priority')
        }),
        ('Booking Details', {
            'fields': (
                'desired_start_time', 'desired_end_time',
                'title', 'description'
            )
        }),
        ('Flexibility Options', {
            'fields': (
                'flexible_start', 'flexible_duration', 
                'min_duration_minutes', 'max_wait_days', 'auto_book'
            )
        }),
        ('Notifications', {
            'fields': (
                'notification_hours_ahead',
            )
        }),
        ('Status Tracking', {
            'fields': ('position', 'times_notified', 'last_notification_sent')
        }),
        ('Booking Outcomes', {
            'fields': ('resulting_booking', 'availability_window_start', 'availability_window_end', 'response_deadline'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'resource')
    
    actions = ['mark_as_expired', 'mark_as_cancelled', 'process_waiting_list']
    
    def mark_as_expired(self, request, queryset):
        """Mark selected entries as expired."""
        updated = queryset.filter(status='active').update(status='expired')
        self.message_user(request, f'Marked {updated} entries as expired.')
    mark_as_expired.short_description = 'Mark selected entries as expired'
    
    def mark_as_cancelled(self, request, queryset):
        """Cancel selected entries."""
        updated = queryset.filter(status__in=['active', 'notified']).update(status='cancelled')
        self.message_user(request, f'Cancelled {updated} entries.')
    mark_as_cancelled.short_description = 'Cancel selected entries'
    
    def process_waiting_list(self, request, queryset):
        """Process waiting list for selected entries' resources."""
        from .waiting_list import waiting_list_service
        
        resources = set(entry.resource for entry in queryset)
        total_notifications = 0
        
        for resource in resources:
            notifications_sent = waiting_list_service.process_waiting_list_for_resource(resource)
            total_notifications += notifications_sent
        
        self.message_user(request, f'Processed waiting lists for {len(resources)} resources. {total_notifications} notifications sent.')
    process_waiting_list.short_description = 'Process waiting list for selected resources'



@admin.register(CheckInOutEvent)
class CheckInOutEventAdmin(admin.ModelAdmin):
    list_display = ('booking', 'event_type', 'user', 'timestamp', 'actual_time')
    list_filter = ('event_type', 'timestamp')
    search_fields = ('booking__title', 'user__username', 'notes')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Event Details', {
            'fields': ('booking', 'event_type', 'user', 'timestamp', 'actual_time')
        }),
        ('Additional Information', {
            'fields': ('notes', 'ip_address', 'user_agent', 'location_data'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('booking__resource', 'user')


@admin.register(UsageAnalytics)
class UsageAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('resource', 'date', 'total_bookings', 'utilization_rate', 'efficiency_rate', 'no_show_rate')
    list_filter = ('date', 'resource__resource_type')
    search_fields = ('resource__name',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('resource', 'date')
        }),
        ('Booking Statistics', {
            'fields': ('total_bookings', 'completed_bookings', 'no_show_bookings', 'cancelled_bookings')
        }),
        ('Time Statistics (Minutes)', {
            'fields': ('total_booked_minutes', 'total_actual_minutes', 'total_wasted_minutes')
        }),
        ('Efficiency Metrics', {
            'fields': ('utilization_rate', 'efficiency_rate', 'no_show_rate')
        }),
        ('Timing Analysis', {
            'fields': (
                'avg_early_checkin_minutes', 'avg_late_checkin_minutes',
                'avg_early_checkout_minutes', 'avg_late_checkout_minutes'
            ),
            'classes': ('collapse',)
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource')


@admin.register(ResourceAccess)
class ResourceAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'access_type', 'granted_by', 'granted_at', 'is_active', 'is_expired')
    list_filter = ('access_type', 'is_active', 'granted_at', 'expires_at')
    search_fields = ('user__username', 'user__email', 'resource__name', 'granted_by__username')
    readonly_fields = ('granted_at',)
    date_hierarchy = 'granted_at'
    
    fieldsets = (
        ('Access Information', {
            'fields': ('user', 'resource', 'access_type', 'is_active')
        }),
        ('Grant Details', {
            'fields': ('granted_by', 'granted_at', 'expires_at')
        }),
        ('Notes', {
            'fields': ('notes',)
        })
    )
    
    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Expired'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'resource', 'granted_by')
    
    actions = ['activate_access', 'deactivate_access', 'extend_access']
    
    def activate_access(self, request, queryset):
        """Activate selected access permissions."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Activated {updated} access permissions.')
    activate_access.short_description = 'Activate selected access permissions'
    
    def deactivate_access(self, request, queryset):
        """Deactivate selected access permissions."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {updated} access permissions.')
    deactivate_access.short_description = 'Deactivate selected access permissions'
    
    def extend_access(self, request, queryset):
        """Extend access by 30 days."""
        from django.utils import timezone
        from datetime import timedelta
        
        count = 0
        for access in queryset:
            if access.expires_at:
                access.expires_at = access.expires_at + timedelta(days=30)
                access.save()
                count += 1
        
        self.message_user(request, f'Extended {count} access permissions by 30 days.')
    extend_access.short_description = 'Extend selected access by 30 days'


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'access_type', 'status', 'created_at', 'reviewed_by', 'reviewed_at')
    list_filter = ('status', 'access_type', 'created_at', 'reviewed_at')
    search_fields = ('user__username', 'user__email', 'resource__name', 'justification', 'review_notes')
    readonly_fields = ('created_at', 'updated_at', 'reviewed_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Request Information', {
            'fields': ('user', 'resource', 'access_type', 'status')
        }),
        ('Request Details', {
            'fields': ('justification', 'requested_duration_days')
        }),
        ('Review Information', {
            'fields': ('reviewed_by', 'reviewed_at', 'review_notes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'resource', 'reviewed_by')
    
    actions = ['approve_requests', 'reject_requests']
    
    def approve_requests(self, request, queryset):
        """Approve selected access requests."""
        count = 0
        for access_request in queryset.filter(status='pending'):
            try:
                access_request.approve(request.user, "Approved via admin action")
                count += 1
            except Exception as e:
                self.message_user(request, f'Error approving request {access_request.id}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Approved {count} access requests.')
    approve_requests.short_description = 'Approve selected requests'
    
    def reject_requests(self, request, queryset):
        """Reject selected access requests."""
        count = 0
        for access_request in queryset.filter(status='pending'):
            try:
                access_request.reject(request.user, "Rejected via admin action")
                count += 1
            except Exception as e:
                self.message_user(request, f'Error rejecting request {access_request.id}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Rejected {count} access requests.')
    reject_requests.short_description = 'Reject selected requests'


@admin.register(TrainingRequest)
class TrainingRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'requested_level', 'current_level', 'status', 'created_at', 'training_date', 'reviewed_by')
    list_filter = ('status', 'requested_level', 'created_at', 'training_date')
    search_fields = ('user__username', 'user__email', 'resource__name', 'justification')
    readonly_fields = ('created_at', 'updated_at', 'reviewed_at', 'completed_date')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Training Request', {
            'fields': ('user', 'resource', 'requested_level', 'current_level', 'status')
        }),
        ('Request Details', {
            'fields': ('justification',)
        }),
        ('Training Schedule', {
            'fields': ('training_date', 'completed_date'),
            'classes': ('collapse',)
        }),
        ('Review Information', {
            'fields': ('reviewed_by', 'reviewed_at', 'review_notes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'resource', 'reviewed_by')
    
    actions = ['schedule_training', 'complete_training', 'cancel_training']
    
    def schedule_training(self, request, queryset):
        """Schedule training for selected requests."""
        from django.utils import timezone
        from datetime import timedelta
        
        count = 0
        training_date = timezone.now() + timedelta(days=7)  # Default to 1 week from now
        
        for training_request in queryset.filter(status='pending'):
            try:
                training_request.schedule_training(
                    training_date=training_date,
                    reviewed_by=request.user,
                    notes="Scheduled via admin action"
                )
                count += 1
            except Exception as e:
                self.message_user(request, f'Error scheduling training for request {training_request.id}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Scheduled training for {count} requests.')
    schedule_training.short_description = 'Schedule training for selected requests'
    
    def complete_training(self, request, queryset):
        """Mark training as completed for selected requests."""
        count = 0
        for training_request in queryset.filter(status__in=['pending', 'scheduled']):
            try:
                training_request.complete_training(request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f'Error completing training for request {training_request.id}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Completed training for {count} requests.')
    complete_training.short_description = 'Mark training as completed'
    
    def cancel_training(self, request, queryset):
        """Cancel selected training requests."""
        updated = queryset.filter(status__in=['pending', 'scheduled']).update(status='cancelled')
        self.message_user(request, f'Cancelled {updated} training requests.')
    cancel_training.short_description = 'Cancel selected training requests'


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value_preview', 'value_type', 'category', 'is_editable', 'updated_at')
    list_filter = ('value_type', 'category', 'is_editable')
    search_fields = ('key', 'description', 'value')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Setting Information', {
            'fields': ('key', 'description', 'category', 'is_editable')
        }),
        ('Value Configuration', {
            'fields': ('value_type', 'value')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def value_preview(self, obj):
        """Show abbreviated value for display."""
        value = obj.value
        if len(value) > 50:
            return f"{value[:47]}..."
        return value
    value_preview.short_description = 'Value'
    
    def get_queryset(self, request):
        return super().get_queryset(request)
    
    actions = ['duplicate_settings', 'export_settings']
    
    def duplicate_settings(self, request, queryset):
        """Duplicate selected settings."""
        duplicated = 0
        for setting in queryset:
            new_key = f"{setting.key}_copy"
            if not SystemSetting.objects.filter(key=new_key).exists():
                SystemSetting.objects.create(
                    key=new_key,
                    value=setting.value,
                    value_type=setting.value_type,
                    description=f"Copy of {setting.description}",
                    category=setting.category,
                    is_editable=setting.is_editable
                )
                duplicated += 1
        
        self.message_user(request, f'Duplicated {duplicated} settings.')
    duplicate_settings.short_description = 'Duplicate selected settings'
    
    def export_settings(self, request, queryset):
        """Export settings as JSON."""
        import json
        from django.http import HttpResponse
        
        settings_data = []
        for setting in queryset:
            settings_data.append({
                'key': setting.key,
                'value': setting.value,
                'value_type': setting.value_type,
                'description': setting.description,
                'category': setting.category,
                'is_editable': setting.is_editable
            })
        
        response = HttpResponse(
            json.dumps(settings_data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="system_settings.json"'
        return response
    export_settings.short_description = 'Export settings as JSON'


@admin.register(PDFExportSettings)
class PDFExportSettingsAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_default', 'default_quality', 'default_orientation', 'organization_name', 'updated_at')
    list_filter = ('is_default', 'default_quality', 'default_orientation', 'include_header', 'include_legend')
    search_fields = ('name', 'description', 'organization_name', 'author_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Configuration Information', {
            'fields': ('name', 'is_default')
        }),
        ('Default Export Settings', {
            'fields': ('default_quality', 'default_orientation')
        }),
        ('Content Options', {
            'fields': (
                ('include_header', 'include_footer'),
                ('include_legend', 'include_details'),
                ('preserve_colors', 'multi_page_support'),
                'compress_pdf'
            )
        }),
        ('Customization', {
            'fields': ('header_logo_url', 'watermark_text', 'custom_css'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('author_name', 'organization_name')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['make_default', 'test_export_config', 'duplicate_config']
    
    def make_default(self, request, queryset):
        """Make selected configuration the default."""
        if queryset.count() != 1:
            self.message_user(request, 'Please select exactly one configuration to make default.', level='ERROR')
            return
        
        config = queryset.first()
        PDFExportSettings.objects.filter(is_default=True).update(is_default=False)
        config.is_default = True
        config.save()
        
        self.message_user(request, f'"{config.name}" is now the default PDF export configuration.')
    make_default.short_description = 'Make selected configuration default'
    
    def test_export_config(self, request, queryset):
        """Test export configuration by generating sample JSON."""
        from django.http import HttpResponse
        import json
        
        configs = []
        for config in queryset:
            configs.append(config.to_json())
        
        response = HttpResponse(
            json.dumps(configs, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="pdf_export_configs.json"'
        return response
    test_export_config.short_description = 'Export configuration as JSON'
    
    def duplicate_config(self, request, queryset):
        """Duplicate selected configurations."""
        duplicated = 0
        for config in queryset:
            new_name = f"{config.name} (Copy)"
            if not PDFExportSettings.objects.filter(name=new_name).exists():
                PDFExportSettings.objects.create(
                    name=new_name,
                    is_default=False,  # Never duplicate as default
                    default_quality=config.default_quality,
                    default_orientation=config.default_orientation,
                    include_header=config.include_header,
                    include_footer=config.include_footer,
                    include_legend=config.include_legend,
                    include_details=config.include_details,
                    preserve_colors=config.preserve_colors,
                    multi_page_support=config.multi_page_support,
                    compress_pdf=config.compress_pdf,
                    header_logo_url=config.header_logo_url,
                    custom_css=config.custom_css,
                    watermark_text=config.watermark_text,
                    author_name=config.author_name,
                    organization_name=config.organization_name
                )
                duplicated += 1
        
        self.message_user(request, f'Duplicated {duplicated} configurations.')
    duplicate_config.short_description = 'Duplicate selected configurations'


# Approval Workflow Admin Classes

@admin.register(ResourceResponsible)
class ResourceResponsibleAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'role_type', 'can_approve_access', 'can_approve_training', 'is_active', 'assigned_at')
    list_filter = ('role_type', 'can_approve_access', 'can_approve_training', 'is_active', 'resource__resource_type')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'resource__name')
    readonly_fields = ('assigned_at',)
    autocomplete_fields = ['user', 'resource', 'assigned_by']
    
    fieldsets = (
        ('Responsibility Assignment', {
            'fields': ('user', 'resource', 'role_type', 'assigned_by')
        }),
        ('Permissions', {
            'fields': ('can_approve_access', 'can_approve_training', 'can_conduct_assessments', 'is_active')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('assigned_at',),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'resource', 'assigned_by')


@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'resource', 'assessment_type', 'risk_level', 'is_mandatory', 'is_active', 'valid_until', 'created_at')
    list_filter = ('assessment_type', 'risk_level', 'is_mandatory', 'is_active', 'requires_renewal', 'resource__resource_type')
    search_fields = ('title', 'resource__name', 'description')
    readonly_fields = ('created_at', 'updated_at', 'approved_at')
    autocomplete_fields = ['resource', 'created_by', 'approved_by']
    
    fieldsets = (
        ('Assessment Information', {
            'fields': ('title', 'resource', 'assessment_type', 'description', 'risk_level')
        }),
        ('Content', {
            'fields': ('hazards_identified', 'control_measures', 'emergency_procedures', 'ppe_requirements'),
            'classes': ('collapse',)
        }),
        ('Lifecycle Management', {
            'fields': ('valid_until', 'review_frequency_months', 'requires_renewal')
        }),
        ('Status', {
            'fields': ('is_active', 'is_mandatory')
        }),
        ('Approval', {
            'fields': ('created_by', 'approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource', 'created_by', 'approved_by')


@admin.register(UserRiskAssessment)
class UserRiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'risk_assessment', 'status', 'score_percentage', 'started_at', 'completed_at', 'expires_at')
    list_filter = ('status', 'risk_assessment__assessment_type', 'risk_assessment__risk_level')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'risk_assessment__title')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'submitted_at', 'completed_at', 'reviewed_at')
    autocomplete_fields = ['user', 'risk_assessment', 'reviewed_by']
    
    fieldsets = (
        ('Assessment Assignment', {
            'fields': ('user', 'risk_assessment', 'status')
        }),
        ('Progress Tracking', {
            'fields': ('started_at', 'submitted_at', 'completed_at', 'expires_at')
        }),
        ('Assessment Results', {
            'fields': ('score_percentage', 'pass_threshold'),
            'classes': ('collapse',)
        }),
        ('Review Information', {
            'fields': ('reviewed_by', 'reviewed_at', 'review_notes'),
            'classes': ('collapse',)
        }),
        ('Assessment Data', {
            'fields': ('responses', 'assessor_notes', 'user_declaration'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'risk_assessment', 'reviewed_by')


@admin.register(TrainingCourse)
class TrainingCourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'course_type', 'delivery_method', 'duration_hours', 'is_active', 'is_mandatory')
    list_filter = ('course_type', 'delivery_method', 'is_active', 'is_mandatory', 'requires_practical_assessment')
    search_fields = ('code', 'title', 'description')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ['created_by', 'instructors', 'prerequisite_courses']
    filter_horizontal = ('instructors', 'prerequisite_courses')
    
    fieldsets = (
        ('Course Information', {
            'fields': ('code', 'title', 'description', 'course_type', 'delivery_method')
        }),
        ('Requirements', {
            'fields': ('prerequisite_courses', 'duration_hours', 'max_participants')
        }),
        ('Content', {
            'fields': ('learning_objectives', 'course_materials', 'assessment_criteria'),
            'classes': ('collapse',)
        }),
        ('Assessment', {
            'fields': ('requires_practical_assessment', 'pass_mark_percentage')
        }),
        ('Validity', {
            'fields': ('valid_for_months',)
        }),
        ('Management', {
            'fields': ('created_by', 'instructors', 'is_active', 'is_mandatory')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by').prefetch_related('instructors')


@admin.register(ResourceTrainingRequirement)
class ResourceTrainingRequirementAdmin(admin.ModelAdmin):
    list_display = ('resource', 'training_course', 'is_mandatory', 'order', 'created_at')
    list_filter = ('is_mandatory', 'resource__resource_type', 'training_course__course_type')
    search_fields = ('resource__name', 'training_course__title', 'training_course__code')
    autocomplete_fields = ['resource', 'training_course']
    
    fieldsets = (
        ('Requirement Definition', {
            'fields': ('resource', 'training_course', 'is_mandatory', 'order')
        }),
        ('Access Control', {
            'fields': ('required_for_access_types',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource', 'training_course')


@admin.register(UserTraining)
class UserTrainingAdmin(admin.ModelAdmin):
    list_display = ('user', 'training_course', 'status', 'overall_score', 'passed', 'completed_at', 'expires_at')
    list_filter = ('status', 'passed', 'training_course__course_type', 'training_course__delivery_method')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'training_course__title', 'certificate_number')
    readonly_fields = ('enrolled_at', 'updated_at', 'certificate_issued_at')
    autocomplete_fields = ['user', 'training_course', 'instructor']
    
    fieldsets = (
        ('Training Assignment', {
            'fields': ('user', 'training_course', 'status')
        }),
        ('Session Details', {
            'fields': ('instructor', 'session_date', 'session_location')
        }),
        ('Progress Tracking', {
            'fields': ('enrolled_at', 'started_at', 'completed_at', 'expires_at')
        }),
        ('Assessment Results', {
            'fields': ('theory_score', 'practical_score', 'overall_score', 'passed'),
            'classes': ('collapse',)
        }),
        ('Feedback', {
            'fields': ('instructor_notes', 'user_feedback'),
            'classes': ('collapse',)
        }),
        ('Certificate', {
            'fields': ('certificate_number', 'certificate_issued_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'training_course', 'instructor')




@admin.register(ApprovalStatistics)
class ApprovalStatisticsAdmin(admin.ModelAdmin):
    list_display = ('resource', 'approver', 'period_display', 'period_type', 'approval_rate', 'response_time_display', 'overdue_items')
    list_filter = ('period_type', 'period_start', 'resource__resource_type', 'approver__userprofile__role')
    search_fields = ('resource__name', 'approver__username', 'approver__email')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'period_start'
    
    fieldsets = (
        ('Period Information', {
            'fields': ('resource', 'approver', 'period_start', 'period_end', 'period_type')
        }),
        ('Access Request Statistics', {
            'fields': (
                'access_requests_received', 'access_requests_approved', 
                'access_requests_rejected', 'access_requests_pending'
            )
        }),
        ('Training Statistics', {
            'fields': (
                'training_requests_received', 'training_sessions_conducted',
                'training_completions', 'training_failures'
            ),
            'classes': ('collapse',)
        }),
        ('Assessment Statistics', {
            'fields': (
                'assessments_created', 'assessments_reviewed',
                'assessments_approved', 'assessments_rejected'
            ),
            'classes': ('collapse',)
        }),
        ('Response Time Metrics', {
            'fields': (
                'avg_response_time_hours', 'min_response_time_hours', 'max_response_time_hours'
            ),
            'classes': ('collapse',)
        }),
        ('Delegation & Overdue', {
            'fields': ('delegations_given', 'delegations_received', 'overdue_items'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def period_display(self, obj):
        return f"{obj.period_start} to {obj.period_end}"
    period_display.short_description = 'Period'
    period_display.admin_order_field = 'period_start'
    
    def approval_rate(self, obj):
        total = obj.access_requests_approved + obj.access_requests_rejected
        if total == 0:
            return "N/A"
        rate = (obj.access_requests_approved / total) * 100
        return f"{rate:.1f}%"
    approval_rate.short_description = 'Approval Rate'
    
    def response_time_display(self, obj):
        if obj.avg_response_time_hours == 0:
            return "N/A"
        return f"{obj.avg_response_time_hours:.1f}h (avg)"
    response_time_display.short_description = 'Avg Response Time'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource', 'approver', 'approver__userprofile')
    
    actions = ['regenerate_statistics', 'export_statistics_csv']
    
    def regenerate_statistics(self, request, queryset):
        """Regenerate statistics for selected periods."""
        count = 0
        for stat in queryset:
            # Call the model method to regenerate statistics
            stat.calculate_statistics()
            count += 1
        
        self.message_user(request, f'Regenerated statistics for {count} periods.')
    regenerate_statistics.short_description = 'Regenerate selected statistics'
    
    def export_statistics_csv(self, request, queryset):
        """Export statistics to CSV."""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="approval_statistics.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Resource', 'Approver', 'Period Start', 'Period End', 'Period Type',
            'Access Requests Received', 'Access Requests Approved', 'Access Requests Rejected',
            'Training Requests', 'Training Completions', 'Assessments Created',
            'Avg Response Time (hours)', 'Overdue Items'
        ])
        
        for stat in queryset:
            writer.writerow([
                stat.resource.name,
                stat.approver.get_full_name() or stat.approver.username,
                stat.period_start,
                stat.period_end,
                stat.get_period_type_display(),
                stat.access_requests_received,
                stat.access_requests_approved,
                stat.access_requests_rejected,
                stat.training_requests_received,
                stat.training_completions,
                stat.assessments_created,
                stat.avg_response_time_hours,
                stat.overdue_items
            ])
        
        return response
    export_statistics_csv.short_description = 'Export selected statistics to CSV'


# Maintenance Management Admin

@admin.register(MaintenanceVendor)
class MaintenanceVendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'email', 'phone', 'is_active', 'contract_active', 'rating')
    list_filter = ('is_active', 'specialties', 'contract_start_date', 'contract_end_date')
    search_fields = ('name', 'contact_person', 'email', 'specialties')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'contact_person', 'email', 'phone', 'address', 'website')
        }),
        ('Capabilities', {
            'fields': ('specialties', 'certifications', 'service_areas')
        }),
        ('Performance', {
            'fields': ('average_response_time', 'rating')
        }),
        ('Business Details', {
            'fields': ('hourly_rate', 'emergency_rate', 'contract_start_date', 'contract_end_date')
        }),
        ('Status', {
            'fields': ('is_active', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def contract_active(self, obj):
        return obj.contract_active
    contract_active.boolean = True
    contract_active.short_description = 'Contract Active'


class MaintenanceDocumentInline(admin.TabularInline):
    model = MaintenanceDocument
    extra = 0
    readonly_fields = ('uploaded_at', 'file_size')
    fields = ('title', 'document_type', 'file', 'is_public', 'uploaded_at')


class MaintenanceAlertInline(admin.TabularInline):
    model = MaintenanceAlert
    extra = 0
    readonly_fields = ('created_at', 'acknowledged_at', 'resolved_at')
    fields = ('alert_type', 'severity', 'title', 'is_active', 'created_at')


@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display = ('title', 'resource', 'maintenance_type', 'priority', 'status', 'start_time', 'vendor', 'actual_cost')
    list_filter = ('maintenance_type', 'priority', 'status', 'is_internal', 'vendor', 'start_time')
    search_fields = ('title', 'description', 'resource__name', 'vendor__name')
    readonly_fields = ('created_at', 'updated_at', 'completed_at', 'cost_variance', 'cost_variance_percentage')
    date_hierarchy = 'start_time'
    inlines = [MaintenanceDocumentInline, MaintenanceAlertInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('resource', 'title', 'description', 'maintenance_type', 'priority', 'status')
        }),
        ('Schedule', {
            'fields': ('start_time', 'end_time', 'is_recurring', 'next_maintenance_date')
        }),
        ('Resource Management', {
            'fields': ('vendor', 'is_internal', 'assigned_to', 'approved_by')
        }),
        ('Cost Tracking', {
            'fields': ('estimated_cost', 'actual_cost', 'labor_hours', 'parts_cost', 'cost_variance', 'cost_variance_percentage')
        }),
        ('Impact', {
            'fields': ('blocks_booking', 'affects_other_resources', 'prerequisite_maintenances')
        }),
        ('Completion', {
            'fields': ('completion_notes', 'issues_found', 'recommendations', 'completed_at'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    filter_horizontal = ('affects_other_resources', 'prerequisite_maintenances')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'resource', 'vendor', 'created_by', 'assigned_to', 'approved_by'
        )
    
    actions = ['mark_completed', 'mark_in_progress', 'calculate_analytics']
    
    def mark_completed(self, request, queryset):
        """Mark selected maintenance as completed."""
        from django.utils import timezone
        updated = 0
        for maintenance in queryset:
            if maintenance.status != 'completed':
                maintenance.status = 'completed'
                maintenance.completed_at = timezone.now()
                maintenance.save()
                updated += 1
        
        self.message_user(request, f'Marked {updated} maintenance items as completed.')
    mark_completed.short_description = 'Mark selected maintenance as completed'
    
    def mark_in_progress(self, request, queryset):
        """Mark selected maintenance as in progress."""
        updated = queryset.exclude(status='completed').update(status='in_progress')
        self.message_user(request, f'Marked {updated} maintenance items as in progress.')
    mark_in_progress.short_description = 'Mark selected maintenance as in progress'
    
    def calculate_analytics(self, request, queryset):
        """Recalculate analytics for resources with selected maintenance."""
        resources = set(maintenance.resource for maintenance in queryset)
        updated = 0
        
        for resource in resources:
            analytics, created = MaintenanceAnalytics.objects.get_or_create(resource=resource)
            analytics.calculate_metrics()
            updated += 1
        
        self.message_user(request, f'Recalculated analytics for {updated} resources.')
    calculate_analytics.short_description = 'Recalculate analytics for affected resources'


@admin.register(MaintenanceDocument)
class MaintenanceDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'maintenance', 'document_type', 'uploaded_by', 'uploaded_at', 'is_public', 'file_size_display')
    list_filter = ('document_type', 'is_public', 'uploaded_at')
    search_fields = ('title', 'description', 'maintenance__title', 'tags')
    readonly_fields = ('uploaded_at', 'file_size')
    
    fieldsets = (
        ('Document Information', {
            'fields': ('maintenance', 'title', 'description', 'document_type')
        }),
        ('File', {
            'fields': ('file', 'file_size')
        }),
        ('Metadata', {
            'fields': ('tags', 'is_public', 'version')
        }),
        ('Upload Info', {
            'fields': ('uploaded_by', 'uploaded_at')
        })
    )
    
    def file_size_display(self, obj):
        if obj.file_size:
            if obj.file_size < 1024:
                return f"{obj.file_size} B"
            elif obj.file_size < 1024 * 1024:
                return f"{obj.file_size / 1024:.1f} KB"
            else:
                return f"{obj.file_size / (1024 * 1024):.1f} MB"
        return "-"
    file_size_display.short_description = 'File Size'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('maintenance', 'uploaded_by')


@admin.register(MaintenanceAlert)
class MaintenanceAlertAdmin(admin.ModelAdmin):
    list_display = ('title', 'resource', 'alert_type', 'severity', 'is_active', 'created_at', 'acknowledged_by')
    list_filter = ('alert_type', 'severity', 'is_active', 'created_at')
    search_fields = ('title', 'message', 'resource__name')
    readonly_fields = ('created_at', 'acknowledged_at', 'resolved_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Alert Information', {
            'fields': ('resource', 'maintenance', 'alert_type', 'severity', 'title')
        }),
        ('Content', {
            'fields': ('message', 'recommendation')
        }),
        ('Metrics', {
            'fields': ('threshold_value', 'actual_value', 'alert_data')
        }),
        ('Status', {
            'fields': ('is_active', 'expires_at')
        }),
        ('Response', {
            'fields': ('acknowledged_by', 'acknowledged_at', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource', 'maintenance', 'acknowledged_by')
    
    actions = ['acknowledge_alerts', 'resolve_alerts', 'extend_expiry']
    
    def acknowledge_alerts(self, request, queryset):
        """Acknowledge selected alerts."""
        updated = 0
        for alert in queryset.filter(acknowledged_by__isnull=True):
            alert.acknowledge(request.user)
            updated += 1
        
        self.message_user(request, f'Acknowledged {updated} alerts.')
    acknowledge_alerts.short_description = 'Acknowledge selected alerts'
    
    def resolve_alerts(self, request, queryset):
        """Resolve selected alerts."""
        updated = 0
        for alert in queryset.filter(resolved_at__isnull=True):
            alert.resolve()
            updated += 1
        
        self.message_user(request, f'Resolved {updated} alerts.')
    resolve_alerts.short_description = 'Resolve selected alerts'
    
    def extend_expiry(self, request, queryset):
        """Extend alert expiry by 7 days."""
        from django.utils import timezone
        from datetime import timedelta
        
        updated = 0
        for alert in queryset.filter(expires_at__isnull=False):
            alert.expires_at = alert.expires_at + timedelta(days=7)
            alert.save()
            updated += 1
        
        self.message_user(request, f'Extended expiry for {updated} alerts.')
    extend_expiry.short_description = 'Extend expiry by 7 days'


@admin.register(MaintenanceAnalytics)
class MaintenanceAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        'resource', 'total_maintenance_count', 'total_maintenance_cost', 
        'preventive_cost_ratio', 'first_time_fix_rate', 'last_calculated'
    )
    list_filter = ('last_calculated',)
    search_fields = ('resource__name',)
    readonly_fields = (
        'total_maintenance_cost', 'average_maintenance_cost', 'preventive_cost_ratio',
        'total_downtime_hours', 'average_repair_time', 'planned_vs_unplanned_ratio',
        'total_maintenance_count', 'preventive_maintenance_count', 'corrective_maintenance_count',
        'emergency_maintenance_count', 'first_time_fix_rate', 'mean_time_between_failures',
        'mean_time_to_repair', 'vendor_performance_score', 'external_maintenance_ratio',
        'last_calculated'
    )
    
    fieldsets = (
        ('Resource', {
            'fields': ('resource',)
        }),
        ('Cost Metrics', {
            'fields': ('total_maintenance_cost', 'average_maintenance_cost', 'preventive_cost_ratio')
        }),
        ('Time Metrics', {
            'fields': ('total_downtime_hours', 'average_repair_time', 'planned_vs_unplanned_ratio')
        }),
        ('Frequency Metrics', {
            'fields': (
                'total_maintenance_count', 'preventive_maintenance_count', 
                'corrective_maintenance_count', 'emergency_maintenance_count'
            )
        }),
        ('Performance Metrics', {
            'fields': ('first_time_fix_rate', 'mean_time_between_failures', 'mean_time_to_repair')
        }),
        ('Vendor Metrics', {
            'fields': ('vendor_performance_score', 'external_maintenance_ratio')
        }),
        ('Predictions', {
            'fields': ('next_failure_prediction', 'failure_probability', 'recommended_maintenance_interval')
        }),
        ('System', {
            'fields': ('last_calculated',)
        })
    )
    
    actions = ['recalculate_metrics']
    
    def recalculate_metrics(self, request, queryset):
        """Recalculate metrics for selected analytics."""
        updated = 0
        for analytics in queryset:
            analytics.calculate_metrics()
            updated += 1
        
        self.message_user(request, f'Recalculated metrics for {updated} resources.')
    recalculate_metrics.short_description = 'Recalculate metrics for selected analytics'


@admin.register(ResourceUtilizationTrend)
class ResourceUtilizationTrendAdmin(admin.ModelAdmin):
    """Admin interface for resource utilization trends."""
    
    list_display = (
        'resource', 'period_type', 'period_start', 'utilization_rate', 
        'actual_usage_rate', 'total_bookings', 'trend_direction', 
        'capacity_status', 'calculated_at'
    )
    
    list_filter = (
        'period_type', 'trend_direction', 
        ('resource', admin.RelatedOnlyFieldListFilter),
        ('period_start', admin.DateFieldListFilter),
        ('calculated_at', admin.DateFieldListFilter)
    )
    
    search_fields = ('resource__name', 'resource__location')
    
    readonly_fields = (
        'efficiency_score', 'demand_score', 'waste_score', 
        'calculated_at', 'updated_at'
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('resource', 'period_type', 'period_start', 'period_end')
        }),
        ('Utilization Metrics', {
            'fields': (
                'total_available_hours', 'total_booked_hours', 'total_used_hours',
                'utilization_rate', 'actual_usage_rate'
            )
        }),
        ('Booking Statistics', {
            'fields': (
                'total_bookings', 'unique_users', 'average_booking_duration',
                'no_show_count', 'no_show_rate'
            )
        }),
        ('Peak Usage Analysis', {
            'fields': ('peak_hour', 'peak_day', 'peak_utilization')
        }),
        ('Trend Analysis', {
            'fields': ('trend_direction', 'trend_strength')
        }),
        ('Capacity Analysis', {
            'fields': (
                'capacity_utilization', 'over_capacity_hours', 'waiting_list_demand'
            )
        }),
        ('Behavior Patterns', {
            'fields': ('user_patterns', 'time_patterns'),
            'classes': ('collapse',)
        }),
        ('Forecasting', {
            'fields': ('forecast_next_period', 'forecast_confidence')
        }),
        ('Calculated Metrics', {
            'fields': ('efficiency_score', 'demand_score', 'waste_score'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('calculated_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['recalculate_trends', 'export_trends']
    
    def capacity_status(self, obj):
        """Display capacity status with color coding."""
        status = obj.get_capacity_status()
        colors = {
            'Over capacity': 'red',
            'Near capacity': 'orange', 
            'High utilization': 'yellow',
            'Moderate utilization': 'green',
            'Low utilization': 'blue'
        }
        color = colors.get(status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color, status
        )
    capacity_status.short_description = 'Capacity Status'
    
    def recalculate_trends(self, request, queryset):
        """Recalculate trends for selected records."""
        from .utilization_service import utilization_service
        
        updated = 0
        for trend in queryset:
            try:
                utilization_service.calculate_utilization_trends(
                    resource=trend.resource,
                    period_type=trend.period_type,
                    start_date=trend.period_start,
                    end_date=trend.period_end,
                    force_recalculate=True
                )
                updated += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f'Error recalculating trend for {trend}: {str(e)}',
                    level='ERROR'
                )
        
        self.message_user(request, f'Recalculated {updated} trends.')
    recalculate_trends.short_description = 'Recalculate selected trends'
    
    def export_trends(self, request, queryset):
        """Export selected trends as CSV."""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="utilization_trends.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Resource', 'Period Type', 'Period Start', 'Period End',
            'Utilization Rate', 'Actual Usage Rate', 'Total Bookings',
            'Unique Users', 'No Show Rate', 'Trend Direction',
            'Trend Strength', 'Capacity Status', 'Efficiency Score'
        ])
        
        for trend in queryset:
            writer.writerow([
                trend.resource.name,
                trend.period_type,
                trend.period_start.strftime('%Y-%m-%d %H:%M'),
                trend.period_end.strftime('%Y-%m-%d %H:%M'),
                float(trend.utilization_rate),
                float(trend.actual_usage_rate),
                trend.total_bookings,
                trend.unique_users,
                float(trend.no_show_rate),
                trend.trend_direction,
                float(trend.trend_strength),
                trend.get_capacity_status(),
                trend.efficiency_score,
            ])
        
        return response
    export_trends.short_description = 'Export selected trends as CSV'


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 1
    fields = ('title', 'item_type', 'is_required', 'order', 'priority')
    ordering = ['order']


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'resource', 'template_type', 'is_active', 'is_mandatory', 'approval_required', 'version', 'created_at')
    list_filter = ('template_type', 'is_active', 'is_mandatory', 'approval_required', 'resource__resource_type')
    search_fields = ('name', 'description', 'resource__name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ChecklistItemInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'resource', 'template_type')
        }),
        ('Configuration', {
            'fields': ('is_active', 'is_mandatory', 'approval_required', 'version')
        }),
        ('Dates', {
            'fields': ('effective_date', 'expiry_date'),
            'classes': ('collapse',)
        }),
        ('Advanced Settings', {
            'fields': ('conditional_logic', 'time_limit_minutes'),
            'classes': ('collapse',)
        }),
        ('Notifications', {
            'fields': ('reminder_enabled', 'reminder_interval_hours'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['duplicate_template', 'activate_templates', 'deactivate_templates']
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def duplicate_template(self, request, queryset):
        """Duplicate selected templates."""
        duplicated = 0
        for template in queryset:
            # Get all items before duplication
            items = list(template.checklist_items.all())
            
            # Duplicate template
            template.pk = None
            template.name = f"{template.name} (Copy)"
            template.version = 1
            template.created_by = request.user
            template.save()
            
            # Duplicate items
            for item in items:
                item.pk = None
                item.template = template
                item.save()
            
            duplicated += 1
        
        self.message_user(request, f'Duplicated {duplicated} templates.')
    duplicate_template.short_description = 'Duplicate selected templates'
    
    def activate_templates(self, request, queryset):
        """Activate selected templates."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Activated {updated} templates.')
    activate_templates.short_description = 'Activate selected templates'
    
    def deactivate_templates(self, request, queryset):
        """Deactivate selected templates."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {updated} templates.')
    deactivate_templates.short_description = 'Deactivate selected templates'


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'template', 'item_type', 'is_required', 'is_active', 'order', 'priority')
    list_filter = ('item_type', 'is_required', 'is_active', 'priority', 'template__resource__resource_type')
    search_fields = ('title', 'description', 'template__name', 'template__resource__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('template', 'title', 'description', 'item_type')
        }),
        ('Configuration', {
            'fields': ('is_required', 'is_active', 'order', 'priority')
        }),
        ('Type-Specific Options', {
            'fields': ('options', 'validation_rules'),
            'classes': ('collapse',)
        }),
        ('Conditional Logic', {
            'fields': ('conditional_logic',),
            'classes': ('collapse',)
        }),
        ('Help & Guidance', {
            'fields': ('help_text', 'help_image'),
            'classes': ('collapse',)
        }),
        ('Issue Escalation', {
            'fields': ('escalation_enabled', 'escalation_contacts'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['duplicate_items', 'activate_items', 'deactivate_items']
    
    def duplicate_items(self, request, queryset):
        """Duplicate selected items."""
        duplicated = 0
        for item in queryset:
            item.pk = None
            item.title = f"{item.title} (Copy)"
            item.save()
            duplicated += 1
        
        self.message_user(request, f'Duplicated {duplicated} items.')
    duplicate_items.short_description = 'Duplicate selected items'
    
    def activate_items(self, request, queryset):
        """Activate selected items."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Activated {updated} items.')
    activate_items.short_description = 'Activate selected items'
    
    def deactivate_items(self, request, queryset):
        """Deactivate selected items."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {updated} items.')
    deactivate_items.short_description = 'Deactivate selected items'


class ChecklistItemCompletionInline(admin.TabularInline):
    model = ChecklistItemCompletion
    extra = 0
    readonly_fields = ('checklist_item', 'response', 'has_issue', 'is_valid', 'completed_at')
    fields = ('checklist_item', 'response', 'has_issue', 'issue_description', 'is_valid')
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChecklistCompletion)
class ChecklistCompletionAdmin(admin.ModelAdmin):
    list_display = ('template', 'user', 'completion_type', 'status', 'completion_percentage', 'has_issues', 'is_overdue_display', 'created_at')
    list_filter = ('status', 'completion_type', 'has_issues', 'template__resource__resource_type', 'created_at')
    search_fields = ('template__name', 'user__username', 'user__email', 'booking__id')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'completed_at', 'approved_at', 'completion_time_seconds')
    inlines = [ChecklistItemCompletionInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('template', 'booking', 'user', 'completion_type', 'status')
        }),
        ('Timestamps', {
            'fields': ('started_at', 'completed_at', 'approved_at', 'due_date', 'completion_time_seconds'),
            'classes': ('collapse',)
        }),
        ('Approval', {
            'fields': ('approved_by', 'approval_notes'),
            'classes': ('collapse',)
        }),
        ('Issues & Escalation', {
            'fields': ('has_issues', 'issues_summary', 'escalated_to', 'escalation_reason'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('ip_address', 'user_agent', 'user_signature', 'supervisor_signature'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['approve_completions', 'reject_completions', 'export_completions']
    
    def completion_percentage(self, obj):
        """Display completion percentage."""
        percentage = obj.get_completion_percentage()
        color = 'green' if percentage == 100 else 'orange' if percentage >= 50 else 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, percentage
        )
    completion_percentage.short_description = 'Completion %'
    
    def is_overdue_display(self, obj):
        """Display overdue status with color coding."""
        if obj.is_overdue():
            return format_html('<span style="color: red;">Overdue</span>')
        elif obj.due_date and obj.status in ['not_started', 'in_progress']:
            return format_html('<span style="color: orange;">Pending</span>')
        else:
            return format_html('<span style="color: green;">On Time</span>')
    is_overdue_display.short_description = 'Due Status'
    
    def approve_completions(self, request, queryset):
        """Bulk approve completed checklists."""
        from .checklist_service import checklist_service
        
        completed_only = queryset.filter(status='completed')
        if not completed_only.exists():
            self.message_user(request, 'No completed checklists selected.', level='WARNING')
            return
        
        approved_count, errors = checklist_service.bulk_approve_checklists(
            completion_ids=list(completed_only.values_list('id', flat=True)),
            approver=request.user,
            notes="Bulk approved via admin interface"
        )
        
        self.message_user(request, f'Approved {approved_count} checklists.')
        if errors:
            for error in errors:
                self.message_user(request, error, level='ERROR')
    approve_completions.short_description = 'Approve selected completed checklists'
    
    def reject_completions(self, request, queryset):
        """Bulk reject completed checklists."""
        from .checklist_service import checklist_service
        
        completed_only = queryset.filter(status='completed')
        rejected_count = 0
        
        for completion in completed_only:
            try:
                checklist_service.reject_checklist(
                    completion,
                    request.user,
                    "Bulk rejected via admin interface"
                )
                rejected_count += 1
            except Exception as e:
                self.message_user(request, f'Error rejecting {completion}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Rejected {rejected_count} checklists.')
    reject_completions.short_description = 'Reject selected completed checklists'
    
    def export_completions(self, request, queryset):
        """Export selected completions as CSV."""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="checklist_completions.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Template', 'Resource', 'User', 'Completion Type', 'Status',
            'Completion %', 'Has Issues', 'Started At', 'Completed At',
            'Approved At', 'Completion Time (seconds)', 'Is Overdue'
        ])
        
        for completion in queryset:
            writer.writerow([
                completion.template.name,
                completion.template.resource.name,
                completion.user.username,
                completion.completion_type,
                completion.status,
                completion.get_completion_percentage(),
                completion.has_issues,
                completion.started_at.strftime('%Y-%m-%d %H:%M:%S') if completion.started_at else '',
                completion.completed_at.strftime('%Y-%m-%d %H:%M:%S') if completion.completed_at else '',
                completion.approved_at.strftime('%Y-%m-%d %H:%M:%S') if completion.approved_at else '',
                completion.completion_time_seconds or 0,
                completion.is_overdue()
            ])
        
        return response
    export_completions.short_description = 'Export selected completions as CSV'


@admin.register(ChecklistItemCompletion)
class ChecklistItemCompletionAdmin(admin.ModelAdmin):
    list_display = ('checklist_completion', 'checklist_item', 'display_response', 'has_issue', 'issue_severity', 'is_valid', 'completed_at')
    list_filter = ('has_issue', 'issue_severity', 'is_valid', 'issue_resolved', 'checklist_item__item_type')
    search_fields = ('checklist_completion__template__name', 'checklist_item__title', 'response', 'issue_description')
    readonly_fields = ('completed_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('checklist_completion', 'checklist_item', 'response', 'file_upload')
        }),
        ('Issue Tracking', {
            'fields': ('has_issue', 'issue_description', 'issue_severity', 'issue_resolved', 'resolution_notes'),
            'classes': ('collapse',)
        }),
        ('Validation', {
            'fields': ('is_valid', 'validation_errors'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('completed_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_issues_resolved', 'revalidate_responses']
    
    def display_response(self, obj):
        """Display formatted response value."""
        return obj.get_display_value()
    display_response.short_description = 'Response'
    
    def mark_issues_resolved(self, request, queryset):
        """Mark selected issues as resolved."""
        issues_only = queryset.filter(has_issue=True, issue_resolved=False)
        resolved_count = 0
        
        for item in issues_only:
            item.resolve_issue("Bulk resolved via admin interface")
            resolved_count += 1
        
        self.message_user(request, f'Resolved {resolved_count} issues.')
    mark_issues_resolved.short_description = 'Mark selected issues as resolved'
    
    def revalidate_responses(self, request, queryset):
        """Revalidate selected responses."""
        revalidated = 0
        for item in queryset:
            item.validate_response()
            item.save()
            revalidated += 1
        
        self.message_user(request, f'Revalidated {revalidated} responses.')
    revalidate_responses.short_description = 'Revalidate selected responses'

