# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django import template
from django.db.models.query import QuerySet
from django.conf import settings
from django.utils import formats
from django.utils.dateformat import format, time_format

from datetime import datetime

from classytags.core import Options, Tag
from classytags.arguments import MultiKeywordArgument, Argument

from rest_framework import exceptions
from rest_framework.generics import get_object_or_404
from rest_framework.renderers import JSONRenderer
from rest_framework.settings import api_settings

from edw.models.entity import EntityModel


register = template.Library()


def from_iso8601(value):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


#==============================================================================
# Common
#==============================================================================
@register.filter(expects_localtime=True, is_safe=False)
def date(value, arg=None):
    """
    Alternative implementation to the built-in `date` template filter which also accepts the
    date string in iso-8601 as passed in by the REST serializers.
    """
    if value in (None, ''):
        return ''
    if not isinstance(value, datetime):
        value = from_iso8601(value)
    if arg is None:
        arg = settings.DATE_FORMAT
    try:
        return formats.date_format(value, arg)
    except AttributeError:
        try:
            return format(value, arg)
        except AttributeError:
            return ''


@register.filter(expects_localtime=True, is_safe=False)
def time(value, arg=None):
    """
    Alternative implementation to the built-in `time` template filter which also accepts the
    date string in iso-8601 as passed in by the REST serializers.
    """
    if value in (None, ''):
        return ''
    if not isinstance(value, datetime):
        value = from_iso8601(value)
    if arg is None:
        arg = settings.TIME_FORMAT
    try:
        return formats.time_format(value, arg)
    except AttributeError:
        try:
            return time_format(value, arg)
        except AttributeError:
            return ''


#==============================================================================
# String utils
#==============================================================================
@register.filter
def split(value, separator):
    """Return the string split by separator.

    Example usage: {{ value|split:"/" }}
    """
    return value.split(separator)


#==============================================================================
# Logical utils
#==============================================================================
@register.filter
def bitwise_and(value, arg):
    return bool(value & arg)


#==============================================================================
# Entities utils
#==============================================================================

class RetrieveDataMixin(object):
    queryset = None
    serializer_class = None

    lookup_field = 'pk'

    # The filter backend classes to use for queryset filtering
    filter_backends = api_settings.DEFAULT_FILTER_BACKENDS

    # The style to use for queryset pagination.
    pagination_class = api_settings.DEFAULT_PAGINATION_CLASS

    permission_classes = api_settings.DEFAULT_PERMISSION_CLASSES

    def permission_denied(self, request, message=None):
        """
        If request is not permitted, determine what kind of exception to raise.
        """
        if not request.successful_authenticator:
            raise exceptions.NotAuthenticated()
        raise exceptions.PermissionDenied(detail=message)

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        return [permission() for permission in self.permission_classes]

    def check_object_permissions(self, request, obj):
        """
        Check if the request should be permitted for a given object.
        Raises an appropriate exception if the request is not permitted.
        """
        for permission in self.get_permissions():
            if not permission.has_object_permission(request, self, obj):
                self.permission_denied(
                    request, message=getattr(permission, 'message', None)
                )

    def render(self, context):
        self.request = context.get('request', None)
        assert self.request is not None, (
            "'%s' `.render()` method parameter `context` should include a `queryset` attribute."
            % self.__class__.__name__
        )
        return super(RetrieveDataMixin, self).render(context)

    def render_tag(self, context, **kwargs):
        return super(RetrieveDataMixin, self).render_tag(context, **kwargs)

    def get_queryset(self):
        """
        Get the list of items for this Tag.
        This must be an iterable, and may be a queryset.
        Defaults to using `self.queryset`.
        """
        assert self.queryset is not None, (
            "'%s' should either include a `queryset` attribute, "
            "or override the `get_queryset()` method."
            % self.__class__.__name__
        )

        queryset = self.queryset
        if isinstance(queryset, QuerySet):
            # Ensure queryset is re-evaluated on each request.
            queryset = queryset.all()
        return queryset

    def filter_queryset(self, queryset):
        """
        Given a queryset, filter it with whichever filter backend is in use.
        """
        for backend in list(self.filter_backends):
            queryset = backend().filter_queryset(self.request, queryset, self)
        return queryset

    def get_object(self):
        """
        Returns the object.
        """
        queryset = self.filter_queryset(self.get_queryset())


        # Perform the lookup filtering.
        filter_kwargs = {self.lookup_field: self.kwargs[self.lookup_field]}
        # todo: fix it!!!!

        print ">>>>>>>", queryset.query
        print self.kwargs


        obj = get_object_or_404(queryset, **filter_kwargs)

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj


class GetEntity(RetrieveDataMixin, Tag):
    name = 'get_entity'
    queryset = EntityModel.objects.all()

    options = Options(
        Argument('pk', resolve=True),
        MultiKeywordArgument('kwargs', required=False),
        'as',
        Argument('varname', required=False, resolve=False)
    )

    def render_tag(self, context, pk, kwargs, varname):
        #entity = get_object_or_404(EntityModel.objects, pk=pk)

        entity = self.get_object()
        print ">>>>>>>>>>>", entity


        data = {
            'Get_entity': "<{}, {}>".format(pk, varname),
            'kwargs': kwargs
        }
        print "+++++++++++++++++++++++"
        print kwargs
        if varname:
            context[varname] = data
            return ''
        else:
            return JSONRenderer().render(data, renderer_context={'indent': kwargs.get('indent', None)})




register.tag(GetEntity)