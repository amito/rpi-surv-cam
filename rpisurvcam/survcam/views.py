import socket
import urllib2
import threading
from os import path, system
from time import sleep
from re import findall
import pika

from django.conf import settings
from django.shortcuts import render, redirect
from django.views.generic import View
from django.views.generic.detail import SingleObjectMixin
from django.http import HttpResponse, HttpResponseBadRequest
from django.http import JsonResponse, FileResponse
from django.template.response import TemplateResponse
from django.core import serializers
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required

from survcam.models import Camera
from events.models import Event, EventClass, get_recent_events, get_motion_events

from .servotargetmanager import ServoTargetManager

# Connect to the servo command queue for later usage by 'move' views
cmd_queue_name = settings.SERVO_CMD_QUEUE
connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
cmd_channel = connection.channel()
cmd_channel.queue_declare(queue = cmd_queue_name)

def get_motion_control_url(request):
    return '%s:%d/0/' % \
        (request.build_absolute_uri('/')[:-1], settings.MOTION_CONTROL_PORT)

def get_motion_stream_url(request):
    return '%s:%d/' % \
        (request.build_absolute_uri('/')[:-1], settings.MOTION_STREAM_PORT)

def get_motion_snapshot_url(request):
    return '%s:%d/0/action/snapshot' % \
        (request.build_absolute_uri('/')[:-1], settings.MOTION_CONTROL_PORT)

def get_motion_query_url(request, param):
    return '%s:%d/0/config/get?query=%s' % \
        (request.build_absolute_uri('/')[:-1], settings.MOTION_CONTROL_PORT, param)

def get_motion_config_param(request, param):
    query_url = get_motion_query_url(request, param)
    try:
        response = urllib2.urlopen(query_url, timeout = 1)
        if response.getcode() != 200:
            return None
        return findall(".*\s=\s(\d+)\s", response.read())[0]
    except:
        return None

def try_set_motion_detection(request, active):
    try:
        action_url = '%s:%d/0/detection/%s' % \
            (request.build_absolute_uri('/')[:-1],
            settings.MOTION_CONTROL_PORT,
            'start' if active else 'pause')
        urllib2.urlopen(action_url).read()
    except:
        pass

def is_stream_alive(request):
    try:
        return urllib2.urlopen(get_motion_stream_url(request),
                               timeout = 2).getcode() == 200
    except:
        return False

def get_camera_details(request):
    last_motion = get_motion_events().first()
    last_motion_time = None if last_motion is None else last_motion.time
    return {
        'res_width': get_motion_config_param(request,'width'),
        'res_height': get_motion_config_param(request,'height'),
        'fps': get_motion_config_param(request,'framerate'),
        'last_motion': last_motion_time,
        'control_url': get_motion_control_url(request)
    }

def file_response(filepath):
    f = open(filepath, 'rb')
    response = FileResponse(f);
    response['Content-Type'] = 'mimetype/submimetype'
    response['Content-Disposition'] = ('attachment; filename=%s' %
    path.basename(path.realpath(f.name)))
    return response

@login_required
def index(request):
    stream_active = is_stream_alive(request)
    return render(
        request,
            'survcam/stream.html',
            {'camera': Camera.objects.first(),
             'camera_details': get_camera_details(request),
             'stream_active': stream_active,
             'stream_url': get_motion_stream_url(request),
             'events': get_recent_events()})

@login_required
def update_status(request):
    events = TemplateResponse(request, 'events/events_contents.html',
                             {'events':get_recent_events()})
    events.render()

    stream_active = is_stream_alive(request)
    stream_status_html = TemplateResponse(request, 'survcam/camera_status.html',
                                     {'camera': Camera.objects.first(),
                                     'camera_details': get_camera_details(request),
                                     'stream_active': stream_active})
    return JsonResponse(
        {'stream_active': stream_active,
        'stream_status_html': stream_status_html.rendered_content,
        'events': events.rendered_content,
        'pan_target': ServoTargetManager().get_target('pan'),
        'tilt_target': ServoTargetManager().get_target('tilt')}, safe=False)

@login_required
def move(request):
    target = request.POST['target']
    axis = request.POST['axis']

    # Disable motion detection before moving the camera
    try_set_motion_detection(request, False)

    cmd_channel.basic_publish(exchange='',
                          routing_key=cmd_queue_name,
                          body=(target + '@' + axis))
    ServoTargetManager().set_target(axis, target)
    
    # Give the servos enough time to move the camera,
    # then enable motion detection
    sleep(2)
    try_set_motion_detection(request, True)

    return JsonResponse({'target': ServoTargetManager().get_target(axis)})

@login_required
def snapshot(request):
    # Ask motion to take a snapshot
    try:
        urllib2.urlopen(get_motion_snapshot_url(request)).read()
    except:
        # motion is probably down, abort
        return HttpResponseBadRequest()
    # Give the file time to be written
    sleep(1)
    # Read file contents and return in response
    snapshot_path = path.join(settings.MOTION_TARGET_DIR,'lastsnap.jpg')
    return file_response(snapshot_path)

@login_required
def download_motion(request):
    if not request.GET.get('filename'):
        # Invalid request
        return redirect('index')

    video_path = path.join(settings.MOTION_TARGET_DIR,request.GET['filename'])
    try:
        return file_response(video_path)
    except:
        # The file may have been deleted after being uploaded to Dropbox,
        # so it's ok to redirect to index, the user will see a new event
        # with a link to the shared Dropbox video.
        return redirect('index')

@staff_member_required
@login_required
@Event.register("Camera turned ON", 'System', Event.EVENT_INFO)
def camera_on(request):
    system('start-stop-daemon --start -o -b --exec ' + settings.MOTION_BIN_PATH)
    return redirect('index')

@staff_member_required
@login_required
@Event.register("Camera turned OFF", 'System', Event.EVENT_INFO)
def camera_off(request):
    system('start-stop-daemon --stop -o --exec ' + settings.MOTION_BIN_PATH)
    return redirect('index')
