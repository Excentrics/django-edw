# -*- coding: utf-8 -*-
from __future__ import unicode_literals


from operator import __or__ as OR

from django.db import models
from django.utils.functional import cached_property

from django_filters.widgets import CSVWidget

import rest_framework_filters as filters

from rest_framework import serializers
from rest_framework.generics import get_object_or_404

from edw.models.entity import BaseEntity
from edw.models.data_mart import DataMartModel
from edw.rest.filters.decorators import get_from_underscore_or_data


class EntityFilter(filters.FilterSet):
    """
    EntityFilter
    """
    #active = filters.BooleanFilter()
    terms = filters.MethodFilter(widget=CSVWidget())
    data_mart_pk = filters.MethodFilter()
    subj = filters.MethodFilter(widget=CSVWidget())
    rel = filters.MethodFilter(widget=CSVWidget())

    class Meta:
        model = BaseEntity
        fields = ['active']

    def __init__(self, *args, **kwargs):
        super(EntityFilter, self).__init__(*args, **kwargs)
        self.data._initial_queryset = self.queryset
        self.data._initial_filter_meta = {}

    @cached_property
    @get_from_underscore_or_data('terms', [], lambda value: value.split(","))
    def term_ids(self, value):
        '''
        :return: `term_ids` value parse from `self._term_ids` or `self.data['terms']`, default: []
        '''
        return serializers.ListField(child=serializers.IntegerField()).to_internal_value(value)

    @cached_property
    @get_from_underscore_or_data('use_cached_decompress', True)
    def use_cached_decompress(self, value):
        '''
        :return: `use_cached_decompress` value parse from `self._use_cached_decompress` or
            `self.data['use_cached_decompress']`, default: True
        '''
        return serializers.BooleanField().to_internal_value(value)

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
        return list(self.data_mart.terms.active().values_list('id', flat=True)) if self.data_mart else []

    def filter_data_mart_pk(self, name, queryset, value):
        self._data_mart_id = value
        if self.data_mart_id is None:
            return queryset

        self.data._initial_queryset = initial_queryset = self.queryset.semantic_filter(
            self.data_mart_term_ids, use_cached_decompress=self.use_cached_decompress)
        self.data._initial_filter_meta = initial_queryset.semantic_filter_meta

        if 'terms' in self.data:
            return queryset

        queryset = queryset.semantic_filter(self.data_mart_term_ids, use_cached_decompress=self.use_cached_decompress)
        self.data._terms_filter_meta = queryset.semantic_filter_meta
        return queryset

    def filter_terms(self, name, queryset, value):
        self._term_ids = value
        if not self.term_ids:
            return queryset
        selected = self.term_ids[:]
        selected.extend(self.data_mart_term_ids)
        queryset = queryset.semantic_filter(selected, use_cached_decompress=self.use_cached_decompress)
        self.data._terms_filter_meta = queryset.semantic_filter_meta
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
        if not self.subj_ids or 'rel' in self.data:
            return queryset
        q_lst = [models.Q(models.Q(forward_relations__to_entity__in=self.subj_ids)),
                 models.Q(backward_relations__from_entity__in=self.subj_ids)]
        return queryset.filter(reduce(OR, q_lst)).distinct()

    @staticmethod
    def _separate_rel_by_key(rel, key, lst):
        i = rel.find(key)
        if i != -1:
            lst.append(long(rel[:i] + rel[i + 1:]))
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
                        rel_b_ids.append(long(x))
        if rel_b_ids:
            rel_f_ids.extend(rel_b_ids)
            rel_r_ids.extend(rel_b_ids)
        return rel_f_ids, rel_r_ids

    def filter_rel(self, name, queryset, value): # todo: move logic to model
        self._rel_ids = value
        if self.rel_ids is None:
            return queryset
        rel_f_ids, rel_r_ids = self.rel_ids
        q_lst = []
        if self.subj_ids:
            if rel_r_ids:
                q_lst.append(models.Q(forward_relations__to_entity__in=self.subj_ids) &
                             models.Q(forward_relations__term__in=rel_r_ids))
            if rel_f_ids:
                q_lst.append(models.Q(backward_relations__from_entity__in=self.subj_ids) &
                             models.Q(backward_relations__term__in=rel_f_ids))
        else:
            if rel_f_ids:
                q_lst.append(models.Q(forward_relations__term__in=rel_f_ids))
            if rel_r_ids:
                q_lst.append(models.Q(backward_relations__rubric__in=rel_r_ids))
        return queryset.filter(reduce(OR, q_lst)).distinct()
