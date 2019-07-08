from django.utils.decorators import method_decorator
from rest_framework.viewsets import ModelViewSet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import DjangoModelPermissions

from fastrunner import models, serializers
from FasterRunner import pagination
from fastrunner.utils import prepare
from fastrunner.utils.decorator import request_log


class TestCaseView(ModelViewSet):
    """
    create:新增测试用例集
        {
            name: str
            project: int,
            relation: int,
            tag:str
            body: [{
                id: int,
                project: int,
                name: str
            }]
        }
    create: copy{
        id: 36
        name: "d"
        project: 6
        relation: 1
        }
    """
    serializer_class = serializers.CaseSerializer
    pagination_class = pagination.MyPageNumberPagination
    permission_classes = (DjangoModelPermissions,)

    def get_queryset(self):
        project = self.request.query_params["project"]
        queryset = models.Case.objects.filter(project__id=project).order_by('-update_time')
        if self.action == 'list':
            node = self.request.query_params["node"]
            search = self.request.query_params["search"]
            if search != '':
                queryset = queryset.filter(name__contains=search)
            if node != '':
                queryset = queryset.filter(relation=node)
        return queryset

    @method_decorator(request_log(level='INFO'))
    def create(self, request, *args, **kwargs):
        if 'id' in request.data.keys():
            pk = request.data['id']
            name = request.data['name']
            case_info = models.Case.objects.get(id=pk)
            request_data = {
                "name": name,
                "relation": case_info.relation,
                "length": case_info.length,
                "tag": case_info.tag,
                "project": case_info.project_id
            }
            serializer = self.get_serializer(data=request_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            case_step = models.CaseStep.objects.filter(case__id=pk)
            for step in case_step:
                step.id = None
                step.case_id = serializer.data["id"]
                step.save()
        else:
            body = request.data.pop('body')
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)

            case = models.Case.objects.filter(**request.data).first()
            prepare.generate_casestep(body, case)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @method_decorator(request_log(level='INFO'))
    def update(self, request, *args, **kwargs):
        body = request.data.pop('body')

        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        prepare.update_casestep(body, instance)

        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    @method_decorator(request_log(level='INFO'))
    def destroy(self, request, *args, **kwargs):
        if kwargs.get('pk') and int(kwargs['pk']) != -1:
            instance = self.get_object()
            prepare.case_end(int(kwargs['pk']))
            self.perform_destroy(instance)
        elif request.data:
            for content in request.data:
                self.kwargs['pk'] = content['id']
                instance = self.get_object()
                prepare.case_end(int(kwargs['pk']))
                self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @method_decorator(request_log(level='INFO'))
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        queryset = models.CaseStep.objects.filter(case__id=kwargs['pk']).order_by('step')
        casestep_serializer = serializers.CaseStepSerializer(queryset, many=True)
        resp = {
            "case": serializer.data,
            "step": casestep_serializer.data
        }
        return Response(resp)

