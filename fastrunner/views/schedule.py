import json
import re

from django.utils.decorators import method_decorator
from rest_framework.viewsets import ModelViewSet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import DjangoModelPermissions
from djcelery import models as celery_models

from FasterRunner import pagination
from fastrunner import serializers
from fastrunner.utils import response
from fastrunner.utils.decorator import request_log


class ScheduleView(ModelViewSet):
    """
    定时任务增删改查
    """
    serializer_class = serializers.PeriodicTaskSerializer
    pagination_class = pagination.MyPageNumberPagination
    permission_classes = (DjangoModelPermissions,)

    def get_queryset(self):
        project = self.request.query_params.get("project")
        return celery_models.PeriodicTask.objects.filter(description=project).order_by('-date_changed')

    @method_decorator(request_log(level='INFO'))
    def create(self, request, *args, **kwargs):
        """新增定时任务{
            name: str
            corntab: str
            switch: bool
            data: [{kwargs: dict,} ,]
            strategy: str
            receiver: str
            copy: str
            project: int,
        }
        """
        request_data = format_request(request.data)
        if not request_data["kwargs"]["receiver"]["success"]:
            return Response(request_data["_email"]["receiver"]["error"], status=status.HTTP_400_BAD_REQUEST)
        if not request_data["kwargs"]["mail_cc"]["success"]:
            return Response(request_data["_email"]["mail_cc"]["error"], status=status.HTTP_400_BAD_REQUEST)
        if request_data["kwargs"]["strategy"] in ['始终发送', '仅失败发送'] and request_data["kwargs"]["receiver"] == []:
            return Response({"receiver": "请填写接收邮箱"}, status=status.HTTP_400_BAD_REQUEST)
        if not request_data["crontab"]["success"]:
            return Response(request_data["crontab"]["error"], status=status.HTTP_400_BAD_REQUEST)
        crontab = celery_models.CrontabSchedule.objects.filter(**request_data["crontab"]["crontab"]).first()
        if crontab is None:
            crontab = serializers.CrontabScheduleSerializer(data=request_data["crontab"]["crontab"])
            crontab.is_valid(raise_exception=True)
            crontab.save()
            crontab = celery_models.CrontabSchedule.objects.filter(**request_data["crontab"]["crontab"]).first()
        request_data["crontab"] = crontab.id
        request_data["kwargs"]["receiver"] = request_data["kwargs"]["receiver"]["email"]
        request_data["kwargs"]["mail_cc"] = request_data["kwargs"]["mail_cc"]["email"]
        request_data["kwargs"] = json.dumps(request_data["kwargs"], ensure_ascii=False)

        serializer = self.get_serializer(data=request_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        request_data = format_request(request.data)
        if not request_data["kwargs"]["receiver"]["success"]:
            return Response(request_data["kwargs"]["receiver"]["error"], status=status.HTTP_400_BAD_REQUEST)
        if not request_data["kwargs"]["mail_cc"]["success"]:
            return Response(request_data["kwargs"]["mail_cc"]["error"], status=status.HTTP_400_BAD_REQUEST)
        if request_data["kwargs"]["strategy"] in ['始终发送', '仅失败发送'] and request_data["kwargs"]["receiver"] == []:
            return Response({"receiver": "请填写接收邮箱"}, status=status.HTTP_400_BAD_REQUEST)
        if not request_data["crontab"]["success"]:
            return Response(request_data["crontab"]["error"], status=status.HTTP_400_BAD_REQUEST)
        crontab = celery_models.CrontabSchedule.objects.filter(**request_data["crontab"]["crontab"]).first()
        if crontab is None:
            crontab = serializers.CrontabScheduleSerializer(data=request_data["crontab"]["crontab"])
            crontab.is_valid(raise_exception=True)
            crontab.save()
        request_data["crontab"] = crontab.id
        request_data["kwargs"]["receiver"] = request_data["kwargs"]["receiver"]["email"]
        request_data["kwargs"]["mail_cc"] = request_data["kwargs"]["mail_cc"]["email"]
        request_data["kwargs"] = json.dumps(request_data["kwargs"], ensure_ascii=False)

        serializer = self.get_serializer(instance, data=request_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)


def format_crontab(crontab_time):
    """
    格式化时间
    """
    crontab_s = crontab_time.strip().split(' ')
    if len(crontab_s) > 5:
        return {"error": {"crontab": "请检查crontab表达式长度"}, "success": False}
    try:
        crontab = {
            'day_of_week': crontab_s[4],
            'month_of_year': crontab_s[3],
            'day_of_month': crontab_s[2],
            'hour': crontab_s[1],
            'minute': crontab_s[0]
        }
        return {"crontab": crontab, "success": True}
    except Exception as e:
        return {"error": {"crontab": "请检查crontab表达式"}, "success": False}


def format_email(email_str):
    """
    :param email_str: str "dasd@qq.com;dasda;dd"
    :return: list
    """
    email_list = []
    if email_str:
        pattern = r'^[a-zA-Z0-9_]+[a-zA-Z0-9_\.]+@[a-zA-Z0-9_]+(\.[a-zA-Z0-9_-]+)+$'
        email_list = [_.strip() for _ in email_str.split(';') if _]
        verfy_email = {}
        for temp_email in email_list:
            if temp_email and re.match(pattern, temp_email) is None:
                verfy_email[temp_email] = "邮箱格式错误"
        if verfy_email:
            return {"error": verfy_email, "email": email_list, "success": False}
    return {"email": email_list, "success": True}


def format_request(request_data):
    _name = request_data.get('name', '')
    _corntab = request_data.get('crontab', '')
    _switch = request_data.get('switch', False)
    _data = request_data.get('data', [])
    _strategy = request_data.get('strategy', '')
    _receiver = request_data.get('receiver', '')
    _mail_cc = request_data.get('mail_cc', '')
    _project = request_data.get('project')

    receiver = format_email(_receiver)
    mail_cc = format_email(_mail_cc)
    crontab_time = format_crontab(_corntab)

    _email = {
        "strategy": _strategy,
        "mail_cc": mail_cc,
        "receiver": receiver,
        "crontab": _corntab,
        "project": _project
    }

    request_data = {
        "name": _name,
        "task": "fastrunner.tasks.schedule_debug_suite",
        "crontab": crontab_time,
        "args": json.dumps(_data, ensure_ascii=False),
        "kwargs": _email,
        "description": _project,
        "enabled": _switch
    }

    return request_data
