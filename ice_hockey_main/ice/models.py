from django.db import models
from django.utils import timezone


class Transmitter(models.Model):
    transmitterSerialNumber = models.CharField(max_length=20)
    nodeType = models.CharField(max_length=20)
    nodeSerialNumber = models.CharField(max_length=20, null=True, blank=True)
    allCount = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['transmitterSerialNumber']),
        ]


class Read(models.Model):
    transmitter = models.ForeignKey(Transmitter, related_name='reads', on_delete=models.CASCADE)
    timeStampUTC = models.DateTimeField(auto_now_add=True)
    lastTimeStamp = models.DateTimeField(null=True)
    deviceUID = models.CharField(max_length=20)
    manufacturerName = models.CharField(max_length=100)
    distance1 = models.IntegerField(null=True, blank=True)
    distance2 = models.IntegerField(null=True, blank=True)
    distance3 = models.IntegerField(null=True, blank=True)
    count = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, default='Out')

    class Meta:
        indexes = [
            models.Index(fields=['deviceUID']),
            models.Index(fields=['timeStampUTC']),
            models.Index(fields=['deviceUID', 'timeStampUTC']),
        ]


class StatusLog(models.Model):
    deviceUID = models.CharField(max_length=255)
    status = models.CharField(max_length=10)
    timestamp = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['deviceUID']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.deviceUID} - {self.status} at {self.timestamp}"


class CommonVideo(models.Model):
    video_file = models.FileField(upload_to='videos/')
    log_date = models.DateField(default=timezone.now)

    def __str__(self):
        return f"Common Video - {self.video_file.name}"


# -----------------------------------------------------------------
# NEW: Maps the raw hardware deviceUID (e.g. "200081") to a simple
# display label (e.g. "1"). This is DISPLAY ONLY -- the real
# deviceUID is still used everywhere else (Read, StatusLog, delete,
# video trimming, JS row IDs, etc.), so nothing else breaks.
#
# To add a new device later: just add a new row here (via Django
# admin, shell, or a management command). No code changes needed.
# -----------------------------------------------------------------
class DeviceLabel(models.Model):
    deviceUID = models.CharField(max_length=20, unique=True)
    label = models.CharField(max_length=20)  # e.g. "1", "2", "3"...

    class Meta:
        indexes = [
            models.Index(fields=['deviceUID']),
        ]
        ordering = ['label']

    def __str__(self):
        return f"{self.deviceUID} -> {self.label}"
