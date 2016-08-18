# -*- coding: utf-8 -*-
from __future__ import unicode_literals

'''
from datetime import datetime
from functools import reduce
import operator
'''
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils import six
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.utils.translation import ugettext_lazy as _
from polymorphic.manager import PolymorphicManager
from polymorphic.models import PolymorphicModel
from polymorphic.base import PolymorphicModelBase

from . import deferred
from .. import settings as edw_settings

#  todo: need refactoring: active, Manager.from_queryset & etc.
#  add semantic_filtering
class BaseEntityManager(PolymorphicManager):
    """
    A base ModelManager for all non-object manipulation needs, mostly statistics and querying.
    """
    '''
    def select_lookup(self, search_term):
        """
        Returning a queryset containing the objects matching the declared lookup fields together
        with the given search term. Each object can define its own lookup fields using the
        member list or tuple `lookup_fields`.
        """
        filter_by_term = (models.Q((sf, search_term)) for sf in self.model.lookup_fields)
        queryset = self.get_queryset().filter(reduce(operator.or_, filter_by_term))
        return queryset
    '''
    def indexable(self):
        """
        Return a queryset of indexable Entities.
        """
        queryset = self.get_queryset().filter(active=True)
        return queryset

    def get_queryset(self):
        return super(BaseEntityManager, self).get_queryset()



class PolymorphicEntityMetaclass(PolymorphicModelBase):
    """
    The BaseEntity class must refer to their materialized model definition, for instance when
    accessing its model manager. Since polymoriphic object classes, normally are materialized
    by more than one model, this metaclass finds the most generic one and associates its
    MaterializedModel with it.
    For instance,``EntityModel.objects.all()`` returns all available objects from the shop.
    """
    def __new__(cls, name, bases, attrs):

        class Meta:
            app_label = edw_settings.APP_LABEL

        attrs.setdefault('Meta', Meta)
        if not hasattr(attrs['Meta'], 'app_label') and not getattr(attrs['Meta'], 'abstract', False):
            attrs['Meta'].app_label = Meta.app_label
        attrs.setdefault('__module__', getattr(bases[-1], '__module__'))

        Model = super(PolymorphicEntityMetaclass, cls).__new__(cls, name, bases, attrs)
        if Model._meta.abstract:
            return Model
        for baseclass in bases:
            # since an abstract base class does not have no valid model.Manager,
            # refer to it via its materialized Entity model.
            if not isinstance(baseclass, cls):
                continue
            try:
                if issubclass(baseclass._materialized_model, Model):
                    # as the materialized model, use the most generic one
                    baseclass._materialized_model = Model
                elif not issubclass(Model, baseclass._materialized_model):
                    raise ImproperlyConfigured("Abstract base class {} has already been associated "
                        "with a model {}, which is different or not a submodel of {}."
                        .format(name, Model, baseclass._materialized_model))
            except (AttributeError, TypeError):
                baseclass._materialized_model = Model
            deferred.ForeignKeyBuilder.process_pending_mappings(Model, baseclass.__name__)

        # search for deferred foreign fields in our Model
        for attrname in dir(Model):
            try:
                member = getattr(Model, attrname)
            except AttributeError:
                continue
            if not isinstance(member, deferred.DeferredRelatedField):
                continue
            map_model = deferred.ForeignKeyBuilder._materialized_models.get(member.abstract_model)
            if map_model:
                field = member.MaterializedField(map_model, **member.options)
                field.contribute_to_class(Model, attrname)
            else:
                deferred.ForeignKeyBuilder._pending_mappings.append((Model, attrname, member,))
        cls.perform_model_checks(Model)
        return Model

    @classmethod
    def perform_model_checks(cls, Model):
        """
        Perform some safety checks on the EntityModel being created.
        """
        if not isinstance(Model.objects, BaseEntityManager):
            msg = "Class `{}.objects` must provide ModelManager inheriting from BaseEntityManager"
            raise NotImplementedError(msg.format(Model.__name__))

        if not isinstance(getattr(Model, 'lookup_fields', None), (list, tuple)):
            msg = "Class `{}` must provide a tuple of `lookup_fields` so that we can easily lookup for Entities"
            raise NotImplementedError(msg.format(Model.__name__))

        try:
            Model().entity_name
        except AttributeError:
            msg = "Class `{}` must provide a model field or property implementing `entity_name`"
            raise NotImplementedError(msg.format(Model.__name__))

        #if not callable(getattr(Model, 'get_price', None)):
        #    msg = "Class `{}` must provide a method implementing `get_price(request)`"
        #    raise NotImplementedError(msg.format(cls.__name__))


@python_2_unicode_compatible
class BaseEntity(six.with_metaclass(PolymorphicEntityMetaclass, PolymorphicModel)):
    """
    An abstract basic object model for the EDW. It is intended to be overridden by one or
    more polymorphic models, adding all the fields and relations, required to describe this
    type of object.

    Some attributes for this class are mandatory. They shall be implemented as property method.
    The following fields MUST be implemented by the inheriting class:
    `entity_name`: Return the pronounced name for this object in its localized language.

    Additionally the inheriting class MUST implement the following methods `get_absolute_url()`
    and etc. See below for details.
    """
    terms = deferred.ManyToManyField('BaseTerm', related_name='entities', verbose_name=_('Terms'), blank=True,
                                     help_text=_("""Use "ctrl" key for choose multiple terms"""))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))
    active = models.BooleanField(default=True, verbose_name=_("Active"),
        help_text=_("Is this object publicly visible."))

    class Meta:
        abstract = True
        verbose_name = _("Entity")
        verbose_name_plural = _("Entities")

    def __str__(self):
        return self.entity_name

    def entity_type(self):
        """
        Returns the polymorphic type of the object.
        """
        return force_text(self.polymorphic_ctype)
    entity_type.short_description = _("Entity type")

    @property
    def entity_model(self):
        """
        Returns the polymorphic model name of the object's class.
        """
        return self.polymorphic_ctype.model

    def get_absolute_url(self):
        """
        Hook for returning the canonical Django URL of this object.
        """
        msg = "Method get_absolute_url() must be implemented by subclass: `{}`"
        raise NotImplementedError(msg.format(self.__class__.__name__))

    '''
    def get_price(self, request):
        """
        Hook for returning the current price of this object.
        The price shall be of type Money. Read the appropriate section on how to create a Money
        type for the chosen currency.
        Use the `request` object to vary the price according to the logged in user,
        its country code or the language.
        """
        msg = "Method get_price() must be implemented by subclass: `{}`"
        raise NotImplementedError(msg.format(self.__class__.__name__))

    def get_availability(self, request):
        """
        Hook for checking the availability of a object. It returns a list of tuples with this
        notation:
        - Number of items available for this object until the specified period expires.
          If this value is ``True``, then infinitely many items are available.
        - Until which timestamp, in UTC, the specified number of items are available.
        This function can return more than one tuple. If the list is empty, then the object is
        considered as not available.
        Use the `request` object to vary the availability according to the logged in user,
        its country code or language.
        """
        return [(True, datetime.max)]  # Infinite number of objects available until eternity

    def is_in_cart(self, cart, watched=False, **kwargs):
        """
        Checks if the object is already in the given cart, and if so, returns the corresponding
        cart_item, otherwise this method returns None.
        The boolean `watched` is used to determine if this check shall only be performed for the
        watch-list.
        Optionally one may pass arbitrary information about the object using `**kwargs`. This can
        be used to determine if a object with variations shall be considered as the same cart item
        increasing it quantity, or if it shall be considered as a separate cart item, resulting in
        the creation of a new cart item.
        """
        from .cart import CartItemModel
        cart_item_qs = CartItemModel.objects.filter(cart=cart, object=self)
        return cart_item_qs.first()
    '''

    def save(self, force_insert=False, force_update=False, *args, **kwargs):
        result = super(BaseEntity, self).save(force_insert, force_update, *args, **kwargs)
        return result


EntityModel = deferred.MaterializedModel(BaseEntity)