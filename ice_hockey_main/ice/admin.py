from django.contrib import admin
from .models import Transmitter, Read, StatusLog, CommonVideo, DeviceLabel


@admin.register(DeviceLabel)
class DeviceLabelAdmin(admin.ModelAdmin):
    list_display = ('deviceUID', 'label')
    search_fields = ('deviceUID', 'label')
    ordering = ('label',)


# Register the rest too, if not already registered elsewhere,
# so you have full visibility/editing from the admin panel.
admin.site.register(Transmitter)
admin.site.register(Read)
admin.site.register(StatusLog)
admin.site.register(CommonVideo)
