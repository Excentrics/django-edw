# -*- coding: utf-8 -*-
from __future__ import unicode_literals


from django.utils import six
from django.utils.functional import cached_property
from django.utils.module_loading import import_string

from django_filters.widgets import CSVWidget

import rest_framework_filters as filters

from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework.filters import OrderingFilter, BaseFilterBackend

from edw.models.entity import BaseEntity
from edw.models.term import TermModel
from edw.models.data_mart import DataMartModel
from edw.rest.filters.decorators import get_from_underscore_or_data


class BaseEntityFilter(filters.FilterSet):
    """
    BaseEntityFilter
    """
    terms = filters.MethodFilter(widget=CSVWidget())
    data_mart_pk = filters.MethodFilter()

    def __init__(self, data, **kwargs):
        try:
            data['_mutable'] = True
        except AttributeError:
            data = data.copy()
        self.patch_data(data, **kwargs)
        super(BaseEntityFilter, self).__init__(data, **kwargs)

    def patch_data(self, data, **kwargs):
        tree = TermModel.cached_decompress([], fix_it=True)
        data.update({
            '_initial_filter_meta': tree,
            '_terms_filter_meta': tree,
            '_data_mart': None
        })

    @cached_property
    @get_from_underscore_or_data('terms', [], lambda value: value.split(","))
    def term_ids(self, value):
        '''
        :return: `term_ids` value parse from `self._term_ids` or `self.data['terms']`, default: []
        '''
        return serializers.ListField(child=serializers.IntegerField()).to_internal_value(value)

    def filter_terms(self, name, queryset, value):
        msg = "Method filter_terms() must be implemented by subclass: `{}`"
        raise NotImplementedError(msg.format(self.__class__.__name__))

    @cached_property
    @get_from_underscore_or_data('data_mart_pk', None)
    def data_mart_id(self, value):
        '''
        :return: `data_mart_id` value parse from `self._data_mart_id` or
            `self.data['data_mart_pk']`, default: None
        '''
        return serializers.IntegerField().to_internal_value(value)

    @cached_property
    def data_mart(self):
        '''
        :return: active `DataMartModel` instance from `self.data_mart_id`
        '''
        pk = self.data_mart_id
        if pk is not None:
            return get_object_or_404(DataMartModel.objects.active(), pk=pk)
        return None

    @cached_property
    def data_mart_term_ids(self):
        return self.data_mart.active_terms_ids if self.data_mart else []

    def filter_data_mart_pk(self, name, queryset, value):
        msg = "Method filter_data_mart_pk() must be implemented by subclass: `{}`"
        raise NotImplementedError(msg.format(self.__class__.__name__))

    @cached_property
    @get_from_underscore_or_data('use_cached_decompress', True)
    def use_cached_decompress(self, value):
        '''
        :return: `use_cached_decompress` value parse from `self._use_cached_decompress` or
            `self.data['use_cached_decompress']`, default: True
        '''
        return serializers.BooleanField().to_internal_value(value)


class EntityFilter(BaseEntityFilter):
    """
    EntityFilter
    """
    active = filters.MethodFilter()
    subj = filters.MethodFilter(widget=CSVWidget())
    rel = filters.MethodFilter(widget=CSVWidget())

    class Meta:
        model = BaseEntity
        fields = []

    def patch_data(self, data, **kwargs):
        data.update({
            '_initial_queryset': kwargs['queryset'],
            '_subj_ids': []
        })
        super(EntityFilter, self).patch_data(data, **kwargs)

    @cached_property
    @get_from_underscore_or_data('active', None)
    def is_active(self, value):
        '''
        :return: `is_active` value parse from `self._active` or
            `self.data['active']`, default: None
        '''
        return serializers.BooleanField().to_internal_value(value)

    def filter_active(self, name, queryset, value):
        self._is_active = value
        if self.is_active is None:
            return queryset
        if self.is_active:
            self.data['_initial_queryset'] = self.data['_initial_queryset'].active()
            queryset = queryset.active()
        else:
            self.data['_initial_queryset'] = self.data['_initial_queryset'].unactive()
            queryset = queryset.unactive()
        return queryset

    @cached_property
    def data_mart_rel_ids(self):
        return ['{}{}'.format(relation.term_id, relation.direction) for relation in
                self.data_mart.relations.all()] if self.data_mart else []

    def filter_data_mart_pk(self, name, queryset, value):
        self._data_mart_id = value
        if self.data_mart_id is None:
            return queryset

        self.data['_data_mart'] = self.data_mart

        if 'rel' not in self.data:
            rel_ids = self.data_mart_rel_ids
            if rel_ids:
                queryset = self.filter_rel(name, queryset, rel_ids)

        self.data['_initial_queryset'] = initial_queryset = self.data['_initial_queryset'].semantic_filter(
            self.data_mart_term_ids, use_cached_decompress=self.use_cached_decompress)
        self.data['_initial_filter_meta'] = initial_queryset.semantic_filter_meta

        if 'terms' in self.data:
            return queryset

        queryset = queryset.semantic_filter(self.data_mart_term_ids, use_cached_decompress=self.use_cached_decompress)
        self.data['_terms_filter_meta'] = queryset.semantic_filter_meta
        return queryset

    def filter_terms(self, name, queryset, value):
        self._term_ids = value
        if not self.term_ids:
            return queryset
        selected = self.term_ids[:]
        selected.extend(self.data_mart_term_ids)
        queryset = queryset.semantic_filter(selected, use_cached_decompress=self.use_cached_decompress)
        self.data['_terms_filter_meta'] = queryset.semantic_filter_meta
        return queryset

    @cached_property
    @get_from_underscore_or_data('subj', [], lambda value: value.split(","))
    def subj_ids(self, value):
        '''
        :return: `subj_ids` value parse from `self._subj_ids` or `self.data['subj']`, default: []
        '''
        return serializers.ListField(child=serializers.IntegerField()).to_internal_value(value)

    def filter_subj(self, name, queryset, value):
        self._subj_ids = value
        if not self.subj_ids:
            return queryset

        self.data['_subj_ids'] = self.subj_ids

        if self.rel_ids is None:
            self.data['_initial_queryset'] = self.data['_initial_queryset'].subj(self.subj_ids)
            return queryset.subj(self.subj_ids)
        else:
            self.data['_initial_queryset'] = self.data['_initial_queryset'].subj_and_rel(self.subj_ids, *self.rel_ids)
            return queryset.subj_and_rel(self.subj_ids, *self.rel_ids)

    @staticmethod
    def _separate_rel_by_key(rel, key, lst):
        i = rel.find(key)
        if i != -1:
            lst.append(int(rel[:i] + rel[i + 1:]))
            return True
        else:
            return False

    @cached_property
    @get_from_underscore_or_data('rel', None, lambda value: value.split(","))
    def rel_ids(self, value):
        """
        `value` - raw relations list
        raw relation item: `id` + `direction`
        direction:
            "b", "" - bidirectional
            "f" - forward
            "r" - reverse
        :return: `relations` ([forward...], [reverse...])
        value parse from `self._rel_ids` or `self.data['rel']`, default: None
        """
        raw_rel = serializers.ListField(child=serializers.RegexField(r'^\d+[bfr]?$')).to_internal_value(value)
        rel_b_ids, rel_f_ids, rel_r_ids = [], [], []
        for x in raw_rel:
            if not EntityFilter._separate_rel_by_key(x, 'b', rel_b_ids):
                if not EntityFilter._separate_rel_by_key(x, 'f', rel_f_ids):
                    if not EntityFilter._separate_rel_by_key(x, 'r', rel_r_ids):
                        rel_b_ids.append(int(x))
        if rel_b_ids:
            rel_f_ids.extend(rel_b_ids)
            rel_r_ids.extend(rel_b_ids)
        return rel_f_ids, rel_r_ids

    def filter_rel(self, name, queryset, value):
        self._rel_ids = value
        if self.rel_ids is None or 'subj' in self.data:
            return queryset

        self.data['_initial_queryset'] = self.data['_initial_queryset'].rel(*self.rel_ids)
        return queryset.rel(*self.rel_ids)


class EntityMetaFilter(BaseFilterBackend):

    def filter_queryset(self, request, queryset, view):

        data_mart = request.GET['_data_mart']

        # annotation & aggregation
        annotation_meta, aggregation_meta = None, None
        if view.action == 'list':
            entity_model = data_mart.entities_model if data_mart is not None else queryset.model

            annotation = entity_model.get_summary_annotation()
            if isinstance(annotation, dict):
                annotation_meta, annotate_kwargs = {}, {}
                for key, value in annotation.items():
                    if isinstance(value, (tuple, list)):
                        annotate_kwargs[key] = value[0]
                        if len(value) > 1:
                            field = value[1]
                            if isinstance(field, six.string_types):
                                field = import_string(field)()
                            annotation_meta[key] = field
                    else:
                        annotate_kwargs[key] = value
                if annotate_kwargs:
                    queryset = queryset.annotate(**annotate_kwargs)

            aggregation = entity_model.get_summary_aggregation()
            if isinstance(aggregation, dict):
                aggregation_meta = {}
                for key, value in aggregation.items():
                    assert isinstance(value, (tuple, list)), (
                        "type of value getting from dictionary key '%s' should be `tuple` or `list`"
                        % key
                    )
                    aggregate = value[0]
                    n = len(value)
                    if n > 1:
                        field = value[1]
                        if isinstance(field, six.string_types):
                            field = import_string(field)()
                        name = value[2] if n > 2 else None
                    else:
                        field, name = None, None
                    aggregation_meta[key] = (aggregate, field, name)

        request.GET['_annotation_meta'] = annotation_meta
        request.GET['_aggregation_meta'] = aggregation_meta

        # select view component
        raw_view_component = request.GET.get('view_component', None)
        if raw_view_component is None:
            view_component = data_mart.view_component if data_mart is not None else None
        else:
            view_component = serializers.CharField().to_internal_value(raw_view_component)
        request.GET['_view_component'] = view_component

        return queryset


class EntityOrderingFilter(OrderingFilter):

    def get_ordering(self, request, queryset, view):
        data_mart = request.GET['_data_mart']
        if data_mart is not None:
            self._extra_ordering = data_mart.entities_model.ORDERING_MODES
            setattr(view, 'ordering', data_mart.ordering)
        result = super(EntityOrderingFilter, self).get_ordering(request, queryset, view)
        request.GET['_ordering'] = result
        return result

    def get_valid_fields(self, queryset, view):
        result = super(EntityOrderingFilter, self).get_valid_fields(queryset, view)
        extra_ordering = getattr(self, '_extra_ordering', None)
        if extra_ordering is not None:
            fields = dict(result)
            fields.update(dict([(item[0].lstrip('-'), item[1]) for item in extra_ordering]))
            result = fields.items()
        return result


