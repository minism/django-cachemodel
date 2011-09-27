#  Copyright 2010 Concentric Sky, Inc. 
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from django.core.cache import cache
from django.db import models
from cachemodel import ns_cache
from cachemodel import mark_all_signatures_as_dirty, key_function_memcache_compat, CACHE_FOREVER_TIMEOUT, CACHEMODEL_DIRTY_SUFFIX
from cachemodel.managers import CacheModelManager, CachedTableManager


from cachemodel.decorators import *   # backwards compatability

class CacheModel(models.Model):
    """An abstract model that has convienence functions for dealing with caching."""
    objects = CacheModelManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        #find all the methods decorated with denormalized_field and update their respective fields
        for method in _find_denormalized_fields(self):
            setattr(self, method._denormalized_field_name, method(self))
        super(CacheModel, self).save(*args, **kwargs)
        self.flush_cache()

    def delete(self, *args, **kwargs):
        super(CacheModel, self).delete(*args, **kwargs)
        self.flush_cache()

    def flush_cache(self):
        """this method is called whenever we should invalidate our cache.

        Instead of deleting from the cache, mark it as dirty instead, to avoid thundering herd problems
        """
        mark_all_signatures_as_dirty("get_cached", self.cache_key)
        mark_all_signatures_as_dirty("cached_method", self.cache_key)

        # Flush the object's namespace cache.
        #self.ns_flush_cache()


    def ns_cache_key(self, *args):
        """Return a cache key inside the object's namespace.

        The namespace is built from: The Objects class.__name__ and the Object's PK.
        """
        return ns_cache.ns_key(self.cache_key(self.pk), args)

    def ns_flush_cache(self):   
        #"""Flush all cache keys inside the object's namespace"""
        #ns_cache.ns_flush(self.cache_key(self.pk))
        """Mark all keys in the namespace as dirty"""
        cache_key = self.cache_key("__namespace__is_dirty__")
        cache.set(cache_key, True, CACHE_FOREVER_TIMEOUT)

    @classmethod
    def cache_key(cls, *args):
        """
        Generates a cache key from the object's class.__name__ and the arguments given
        """
        return ':'.join([cls.__name__] + [key_function_memcache_compat(arg) for arg in args])

    def warm_cache(self):
        pass

    def __getattr__(self, name):
        if name.endswith('_cached'):
            field_name = name[:-7]
            field = self._meta.get_field(field_name)
            if isinstance(field, models.ForeignKey):
                related_model = field.related.parent_model
                related_id = getattr(self, '%s_id' % field_name)
                if issubclass(related_model.objects.__class__, CacheModelManager):
                    return related_model.objects.get_cached(pk=related_id)
                else:
                    return getattr(self, field_name)
        raise AttributeError("'%s' object has no attribute '%s'" % (self._meta.object_name, name,))

def _find_denormalized_fields(instance):
    """helper function that finds all methods decorated with @denormalized_field"""
    non_field_attributes = set(dir(instance.__class__)) - set(instance._meta.get_all_field_names())
    for m in non_field_attributes:
        if hasattr(getattr(instance.__class__, m), '_denormalized_field'):
            yield getattr(instance.__class__, m)


class CachedTable(CacheModel):
    """A convience class that loads the entire table into the cache ONLY USE FOR SMALL TABLES.

    Intended for use for things like Category tables, that will be < 50 entries and used heavily.
    """
    objects = CachedTableManager()

    class Meta:
        abstract = True
