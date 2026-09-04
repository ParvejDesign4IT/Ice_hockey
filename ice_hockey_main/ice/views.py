import os
import math
import json
import subprocess
from datetime import datetime, timedelta, timezone as dt_timezone, time

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from django.db.models import Subquery, OuterRef

from moviepy.video.io.VideoFileClip import VideoFileClip

from .models import Read, StatusLog, Transmitter, CommonVideo, DeviceLabel
from .serializers import TransmitterSerializer


DEVICE_CACHE = {}


# ---------------------------------------------------------------------------
# Transmitter ingest
# ---------------------------------------------------------------------------

@api_view(['POST'])
def create_transmitter(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            print("Received POST data:", data)
            print("------------------------------------------------------------------------------------------------------------------------------------")
            transmitter_serial_number = data.get('transmitterSerialNumber', '')
            existing_transmitter = Transmitter.objects.filter(transmitterSerialNumber=transmitter_serial_number).first()

            if existing_transmitter:
                serializer = TransmitterSerializer(existing_transmitter, data=data)
            else:
                serializer = TransmitterSerializer(data=data)

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data,
                                 status=status.HTTP_200_OK if existing_transmitter else status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print("Error processing POST data:", e)
            return Response({'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'message': 'Method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


# ---------------------------------------------------------------------------
# Shared helper — used by both transmitter_list and transmitter_data_json
# ---------------------------------------------------------------------------

def _sort_key(label):
    """Numeric-aware sort: '2' before '10'; numbers before non-numeric labels."""
    label_str = str(label)
    return (0, int(label_str)) if label_str.isdigit() else (1, label_str)


def get_aggregated_device_data():
    """
    Latest reading per device, with friendly label attached and a
    basic In/Out 'status' computed from distance thresholds.
    Sorted ascending by Player No / label.
    Shared by transmitter_list (page load) and transmitter_data_json (polling).
    """
    latest_subquery = Read.objects.filter(
        deviceUID=OuterRef('deviceUID')
    ).order_by('-timeStampUTC').values('id')[:1]

    recent_reads = Read.objects.filter(
        id__in=Subquery(latest_subquery)
    ).select_related('transmitter')

    label_map = dict(DeviceLabel.objects.values_list('deviceUID', 'label'))

    device_data = {}

    for read in recent_reads:
        device_uid = read.deviceUID

        if device_uid not in device_data:
            device_data[device_uid] = {
                'deviceUID': device_uid,
                'label': label_map.get(device_uid, device_uid),
                'distance1': None,
                'distance2': None,
                'distance3': None,
                'position': None,
                'timeStampUTC': read.timeStampUTC,
                'lastTimeStamp': read.lastTimeStamp,
                'status': read.status,
                'inout_status': 'Unknown',
                'distance1_last_update': None,
                'distance2_last_update': None,
                'distance3_last_update': None,
            }
        else:
            device_data[device_uid]['label'] = label_map.get(device_uid, device_uid)

        transmitter_serial = read.transmitter.transmitterSerialNumber if read.transmitter else None

        if transmitter_serial == '1000CB':
            device_data[device_uid]['distance1'] = read.distance1 or device_data[device_uid]['distance1']
            device_data[device_uid]['distance1_last_update'] = read.timeStampUTC
        elif transmitter_serial == '1000ED':
            device_data[device_uid]['distance2'] = read.distance2 or device_data[device_uid]['distance2']
            device_data[device_uid]['distance2_last_update'] = read.timeStampUTC
        elif transmitter_serial == '10012B':
            device_data[device_uid]['distance3'] = read.distance3 or device_data[device_uid]['distance3']
            device_data[device_uid]['distance3_last_update'] = read.timeStampUTC

        device_data[device_uid]['lastTimeStamp'] = read.lastTimeStamp

        if read.timeStampUTC > device_data[device_uid]['timeStampUTC']:
            device_data[device_uid]['timeStampUTC'] = read.timeStampUTC

        distances = [
            device_data[device_uid]['distance1'],
            device_data[device_uid]['distance2'],
            device_data[device_uid]['distance3'],
        ]
        if any(d is not None and d > 1500 for d in distances):
            device_data[device_uid]['status'] = 'Out'
        else:
            device_data[device_uid]['status'] = 'In'

    return sorted(device_data.values(), key=lambda d: _sort_key(d['label']))


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

def transmitter_list(request):
    aggregated_reads = get_aggregated_device_data()
    return render(request, 'ViewPage.html', {'aggregated_reads': aggregated_reads})


def status_log_view(request):
    status_logs = StatusLog.objects.all()
    return render(request, 'status_log.html', {'status_logs': status_logs})


# ---------------------------------------------------------------------------
# Polling / JSON endpoints
# ---------------------------------------------------------------------------

def transmitter_data_json(request):
    """
    Returns JSON for all devices: latest readings, computed IN/OUT,
    Active/Inactive status, friendly label, server UTC timestamp.
    Uses DEVICE_CACHE to persist state (e.g. Active/Inactive) between polls.
    """
    aggregated_reads = get_aggregated_device_data()
    server_utc_now = now()

    for read in aggregated_reads:
        device_uid = read['deviceUID']

        if device_uid not in DEVICE_CACHE:
            DEVICE_CACHE[device_uid] = {
                'deviceUID': device_uid,
                'label': read['label'],
                'distance1': None,
                'distance2': None,
                'distance3': None,
                'position': None,
                'timeStampUTC': None,
                'lastTimeStamp': None,
                'status': 'Inactive',
                'inout_status': 'Unknown',
                'distance1_last_update': None,
                'distance2_last_update': None,
                'distance3_last_update': None,
            }

        cache_entry = DEVICE_CACHE[device_uid]
        cache_entry['label'] = read['label']

        if read['distance1'] is not None:
            cache_entry['distance1'] = read['distance1']
            cache_entry['distance1_last_update'] = read['distance1_last_update']
        if read['distance2'] is not None:
            cache_entry['distance2'] = read['distance2']
            cache_entry['distance2_last_update'] = read['distance2_last_update']
        if read['distance3'] is not None:
            cache_entry['distance3'] = read['distance3']
            cache_entry['distance3_last_update'] = read['distance3_last_update']

        cache_entry['timeStampUTC'] = (
            read['timeStampUTC'].astimezone(dt_timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            if read['timeStampUTC'] else None
        )
        cache_entry['lastTimeStamp'] = (
            read['lastTimeStamp'].astimezone(dt_timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            if read['lastTimeStamp'] else None
        )

    # --- Status + In/Out + StatusLog (stateful — stays in this view) ---
    for device_uid, data in DEVICE_CACHE.items():
        distances = [data['distance1'], data['distance2'], data['distance3']]
        valid_distances = [d for d in distances if isinstance(d, (int, float))]

        if valid_distances:
            if any(d > 1500 for d in valid_distances):
                data['inout_status'] = 'Out'
            elif any(d < 1500 for d in valid_distances):
                data['inout_status'] = 'In'

        last_updates = [
            data['distance1_last_update'],
            data['distance2_last_update'],
            data['distance3_last_update'],
        ]
        new_status = (
            'Active'
            if any(ts and (server_utc_now - ts <= timedelta(seconds=20)) for ts in last_updates)
            else 'Inactive'
        )
        data['status'] = new_status

        statuslog_status = None
        if new_status == 'Inactive':
            data['inout_status'] = 'Out'
            statuslog_status = 'Out'
        elif new_status == 'Active' and valid_distances:
            if any(d > 1500 for d in valid_distances):
                statuslog_status = 'In'
            elif any(d < 1500 for d in valid_distances):
                statuslog_status = 'Out'

        if statuslog_status:
            last_log = StatusLog.objects.filter(deviceUID=device_uid).order_by('-timestamp').first()
            if not last_log or last_log.status != statuslog_status:
                StatusLog.objects.create(
                    deviceUID=device_uid,
                    status=statuslog_status,
                    timestamp=server_utc_now
                )

    # --- Remove stale devices ---
    stale_threshold = timedelta(minutes=30)
    stale_devices = [
        uid for uid, data in DEVICE_CACHE.items()
        if data['lastTimeStamp'] and (server_utc_now - now() > stale_threshold)
    ]
    for uid in stale_devices:
        DEVICE_CACHE.pop(uid, None)

    aggregated_output = sorted(DEVICE_CACHE.values(), key=lambda d: _sort_key(d['label']))

    return JsonResponse({
        'reads': aggregated_output,
        'timestamp': server_utc_now.isoformat(),
        'count': len(aggregated_output)
    })


def status_log_json(request):
    logs = StatusLog.objects.order_by('-timestamp')[:250]
    label_map = dict(DeviceLabel.objects.values_list('deviceUID', 'label'))

    data = [
        {
            "deviceUID": log.deviceUID,
            "label": label_map.get(log.deviceUID, log.deviceUID),
            "status": log.status,
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        for log in logs
    ]

    return JsonResponse({"status_logs": data})


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def custom_404_view(request, exception):
    return render(request, '404.html', status=404)


@csrf_exempt
def delete_read(request, device_uid):
    if request.method == 'POST':
        try:
            last_log = StatusLog.objects.filter(deviceUID=device_uid).order_by('-timestamp').first()

            if not last_log or last_log.status != 'Out':
                StatusLog.objects.create(
                    deviceUID=device_uid,
                    status='Out',
                    timestamp=now()
                )

            reads = Read.objects.filter(deviceUID=device_uid)
            if reads.exists():
                reads.delete()

            if device_uid in DEVICE_CACHE:
                del DEVICE_CACHE[device_uid]

            return JsonResponse({
                'success': True,
                'message': f"Device {device_uid} deleted and forced OUT status logged."
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=400)


# ---------------------------------------------------------------------------
# Video trimming
# ---------------------------------------------------------------------------

def trim_video(request):
    cleanup_expired_videos()   # NEW: remove any videos from past dates first 

    distinct_uids = StatusLog.objects.values_list("deviceUID", flat=True).distinct()
    label_map = dict(DeviceLabel.objects.values_list('deviceUID', 'label'))

    distinct_device_count = sorted(
        [
            {"deviceUID": uid, "label": label_map.get(uid, uid)}
            for uid in distinct_uids
        ],
        key=lambda d: _sort_key(d["label"])
    )

    if request.method == "POST":
        device_uid = request.POST.get("device_uid")
        log_date = request.POST.get("log_date")
        game_start_time = request.POST.get("game_start_time")

        if not (device_uid and log_date and game_start_time):
            return render(request, "trim_video.html", {
                "distinct_device_count": distinct_device_count,
                "error_message": "All fields are required."
            })

        naive_game_start = datetime.strptime(f"{log_date} {game_start_time}", "%Y-%m-%d %H:%M:%S")
        game_start_dt = timezone.make_aware(naive_game_start, timezone.get_current_timezone())
        selected_date = naive_game_start.date()

        logs = StatusLog.objects.filter(
            deviceUID=device_uid,
            timestamp__date=selected_date,
            timestamp__gte=game_start_dt
        ).order_by("timestamp")

        if not logs.exists():
            return render(request, "trim_video.html", {
                "distinct_device_count": distinct_device_count,
                "error_message": "No Active/Inactive logs after game start time."
            })

        video_obj = CommonVideo.objects.filter(log_date=selected_date).order_by("id").first()
        if not video_obj or not video_obj.video_file:
            return render(request, "trim_video.html", {
                "distinct_device_count": distinct_device_count,
                "error_message": f"No uploaded video found for {selected_date}."
            })

        video_path = video_obj.video_file.path
        temp_dir = os.path.join(settings.MEDIA_ROOT, "temp")
        os.makedirs(temp_dir, exist_ok=True)

        segment_files = []
        active_start = None
        index = 0
        fallback_used = False

        for log in logs:
            if log.status == "In":
                active_start = log.timestamp

            elif log.status == "Out" and active_start:
                start_offset = (active_start - game_start_dt).total_seconds()
                duration = (log.timestamp - active_start).total_seconds() + 1

                if duration > 0:
                    segment_path = os.path.join(temp_dir, f"segment_{index}.mp4")
                    subprocess.run(
                        [
                            settings.FFMPEG_BINARY, "-y",
                            "-ss", str(start_offset),
                            "-i", video_path,
                            "-t", str(duration),
                            "-c:v", "libx264",
                            "-c:a", "aac",
                            "-preset", "veryfast",
                            "-movflags", "+faststart",
                            segment_path
                        ],
                        check=True
                    )
                    segment_files.append(segment_path)
                    index += 1

                active_start = None

        if active_start:
            video_clip = VideoFileClip(video_path)
            video_duration = video_clip.duration
            video_clip.close()

            start_offset = (active_start - game_start_dt).total_seconds()
            remaining_duration = max(video_duration - start_offset, 0)

            if remaining_duration > 0:
                segment_path = os.path.join(temp_dir, f"segment_{index}.mp4")
                subprocess.run(
                    [
                        settings.FFMPEG_BINARY, "-y",
                        "-ss", str(start_offset),
                        "-i", video_path,
                        "-t", str(remaining_duration),
                        "-c:v", "libx264",
                        "-c:a", "aac",
                        "-preset", "veryfast",
                        "-movflags", "+faststart",
                        segment_path
                    ],
                    check=True
                )
                segment_files.append(segment_path)
                fallback_used = True

        if not segment_files:
            return render(request, "trim_video.html", {
                "distinct_device_count": distinct_device_count,
                "error_message": "No valid Active → Inactive segments found."
            })

        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for seg in segment_files:
                safe_seg = seg.replace("\\", "/")
                f.write(f"file '{safe_seg}'\n")

        output_name = f"trimmed_{device_uid}_{selected_date}.mp4"
        output_path = os.path.join(settings.MEDIA_ROOT, output_name)

        subprocess.run(
            [
                settings.FFMPEG_BINARY, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_path
            ],
            check=True
        )

        for f in segment_files + [concat_file]:
            if os.path.exists(f):
                os.remove(f)

        return render(request, "trim_video.html", {
            "distinct_device_count": distinct_device_count,
            "download_url": settings.MEDIA_URL + output_name,
            "success_message": (
                "No inactive logs found after game start time."
                if fallback_used else
                "Video trimmed and merged successfully!"
            )
        })

    return render(request, "trim_video.html", {"distinct_device_count": distinct_device_count})


def check_statuslog(request):
    """
    AJAX view to check if StatusLog and CommonVideo are available for the selected UID and date.
    """
    device_uid = request.GET.get('device_uid')
    date_str = request.GET.get('date')

    if not device_uid or not date_str:
        return JsonResponse({'available': False, 'message': 'Invalid parameters.'})

    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        status_logs = StatusLog.objects.filter(deviceUID=device_uid, timestamp__date=selected_date)
        logs_exist = status_logs.exists()
        log_count = status_logs.count()

        video_exist = CommonVideo.objects.filter(log_date=selected_date).exists()

        if logs_exist and video_exist:
            if log_count % 2 == 0:
                return JsonResponse({'available': True, 'message': f'Status logs ({log_count} entries) and video available for the selected device and date.'})
            else:
                return JsonResponse({'available': False, 'message': f'Status logs ({log_count} entries) available, but uneven number (need IN-OUT pairs). Video found.'})
        elif logs_exist:
            return JsonResponse({'available': False, 'message': f'Status logs ({log_count} entries) available, but no video found for the selected date.'})
        elif video_exist:
            return JsonResponse({'available': False, 'message': 'Video available, but no status logs found for the selected device and date.'})
        else:
            return JsonResponse({'available': False, 'message': 'No status logs or video found for the selected device and date.'})

    except ValueError:
        return JsonResponse({'available': False, 'message': 'Invalid date format.'})

def cleanup_expired_videos():
    """
    Deletes any CommonVideo whose log_date is more than 7 days old,
    removing both the DB record and the file from disk.
    """
    cutoff_date = timezone.localdate() - timedelta(days=7)
    expired_videos = CommonVideo.objects.filter(log_date__lt=cutoff_date)

    for video in expired_videos:
        if video.video_file and os.path.exists(video.video_file.path):
            os.remove(video.video_file.path)
        video.delete()



def upload_video(request):
    cleanup_expired_videos()   # NEW: remove any videos from past dates first

    if request.method == "POST":
        video_file = request.FILES.get("video_file")
        log_date = request.POST.get("log_date")

        if not video_file or not log_date:
            messages.error(request, "Please select a valid video file and date.")
            return redirect("upload_video")

        try:
            existing_video = CommonVideo.objects.filter(log_date=log_date).first()

            if existing_video:
                if existing_video.video_file and os.path.exists(existing_video.video_file.path):
                    os.remove(existing_video.video_file.path)
                existing_video.video_file = video_file
                existing_video.save()
                messages.success(request, f"Video for {log_date} replaced successfully.")
            else:
                CommonVideo.objects.create(video_file=video_file, log_date=log_date)
                messages.success(request, f"New video uploaded successfully for {log_date}.")

        except Exception as e:
            messages.error(request, f"Upload failed: {str(e)}")

        return redirect("upload_video")

    return render(request, "upload_video.html")


def check_video_availability(request):
    cleanup_expired_videos()   # NEW: remove any videos from past dates first

    date_str = request.GET.get('date')

    if not date_str:
        return JsonResponse({'available': False})

    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        video = CommonVideo.objects.filter(log_date=selected_date).first()

        if not video or not video.video_file:
            return JsonResponse({'available': False})

        if not os.path.exists(video.video_file.path):
            return JsonResponse({'available': False})

        return JsonResponse({'available': True})

    except Exception:
        return JsonResponse({'available': False})


def check_statuslog_availability(request):
    device_uid = request.GET.get('device_uid')
    date_str = request.GET.get('date')

    if not device_uid or not date_str:
        return JsonResponse({'available': False, 'message': 'Device UID or date not provided'})

    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        start_datetime = timezone.make_aware(datetime.combine(selected_date, time.min), timezone.utc)
        end_datetime = timezone.make_aware(datetime.combine(selected_date, time.max), timezone.utc)

        status_logs = StatusLog.objects.filter(
            deviceUID=device_uid,
            timestamp__gte=start_datetime,
            timestamp__lte=end_datetime
        ).order_by('timestamp')

        if status_logs.exists():
            return JsonResponse({
                'available': True,
                'message': f"{status_logs.count()} log(s) found for device {device_uid} on {selected_date}"
            })
        else:
            return JsonResponse({
                'available': False,
                'message': f"No logs found for device {device_uid} on {selected_date}"
            })

    except Exception as e:
        return JsonResponse({'available': False, 'message': f'Error: {str(e)}'})