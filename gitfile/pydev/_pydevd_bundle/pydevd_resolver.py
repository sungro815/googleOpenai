try:
    import StringIO
except:
    import io as StringIO
import traceback
import warnings
from contextlib import contextmanager
from os.path import basename

from _pydevd_bundle import pydevd_constants
from _pydevd_bundle.pydevd_constants import dict_iter_items, dict_keys, xrange, IS_PYCHARM
from _pydevd_bundle.pydevd_utils import get_var_and_offset


# Note: 300 is already a lot to see in the outline (after that the user should really use the shell to get things)
# and this also means we'll pass less information to the client side (which makes debugging faster).
MAX_ITEMS_TO_HANDLE = 300 if not IS_PYCHARM else 100

TOO_LARGE_MSG = 'Too large to show contents. Max items to show: ' + str(MAX_ITEMS_TO_HANDLE)
TOO_LARGE_ATTR = 'Unable to handle:'

#=======================================================================================================================
# UnableToResolveVariableException
#=======================================================================================================================
class UnableToResolveVariableException(Exception):
    pass


#=======================================================================================================================
# InspectStub
#=======================================================================================================================
class InspectStub:
    def isbuiltin(self, _args):
        return False
    def isroutine(self, object):
        return False

try:
    import inspect
except:
    inspect = InspectStub()

try:
    from collections import OrderedDict
except:
    OrderedDict = dict

try:
    import java.lang #@UnresolvedImport
except:
    pass

#types does not include a MethodWrapperType
try:
    MethodWrapperType = type([].__str__)
except:
    MethodWrapperType = None


@contextmanager
def suppress_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


#=======================================================================================================================
# See: pydevd_extension_api module for resolver interface
#=======================================================================================================================


#=======================================================================================================================
# DefaultResolver
#=======================================================================================================================
class DefaultResolver:
    '''
        DefaultResolver is the class that'll actually resolve how to show some variable.
    '''

    def resolve(self, var, attribute):
        with suppress_warnings():
            return getattr(var, attribute)

    def get_dictionary(self, var, names=None):
        if MethodWrapperType:
            return self._getPyDictionary(var, names)
        else:
            return self._getJyDictionary(var)

    def _getJyDictionary(self, obj):
        ret = {}
        found = java.util.HashMap()

        original = obj
        if hasattr(obj, '__class__') and obj.__class__ == java.lang.Class:

            #get info about superclasses
            classes = []
            classes.append(obj)
            c = obj.getSuperclass()
            while c != None:
                classes.append(c)
                c = c.getSuperclass()

            #get info about interfaces
            interfs = []
            for obj in classes:
                interfs.extend(obj.getInterfaces())
            classes.extend(interfs)

            #now is the time when we actually get info on the declared methods and fields
            for obj in classes:

                declaredMethods = obj.getDeclaredMethods()
                declaredFields = obj.getDeclaredFields()
                for i in xrange(len(declaredMethods)):
                    name = declaredMethods[i].getName()
                    ret[name] = declaredMethods[i].toString()
                    found.put(name, 1)

                for i in xrange(len(declaredFields)):
                    name = declaredFields[i].getName()
                    found.put(name, 1)
                    #if declaredFields[i].isAccessible():
                    declaredFields[i].setAccessible(True)
                    #ret[name] = declaredFields[i].get( declaredFields[i] )
                    try:
                        ret[name] = declaredFields[i].get(original)
                    except:
                        ret[name] = declaredFields[i].toString()

        #this simple dir does not always get all the info, that's why we have the part before
        #(e.g.: if we do a dir on String, some methods that are from other interfaces such as
        #charAt don't appear)
        try:
            d = dir(original)
            for name in d:
                if found.get(name) != 1:
                    ret[name] = getattr(original, name)
        except:
            #sometimes we're unable to do a dir
            pass

        return ret

    def get_names(self, var):
        names = dir(var)
        if not names and hasattr(var, '__members__'):
            names = var.__members__
        return names

    def _getPyDictionary(self, var, names=None):
        filterPrivate = False
        filterSpecial = True
        filterFunction = True
        filterBuiltIn = True

        if not names:
            names = self.get_names(var)
        d = OrderedDict()

        #Be aware that the order in which the filters are applied attempts to
        #optimize the operation by removing as many items as possible in the
        #first filters, leaving fewer items for later filters

        if filterBuiltIn or filterFunction:
            for n in names:
                if filterSpecial:
                    if n.startswith('__') and n.endswith('__'):
                        continue

                if filterPrivate:
                    if n.startswith('_') or n.endswith('__'):
                        continue

                try:
                    with suppress_warnings():
                        attr = getattr(var, n)

                    #filter builtins?
                    if filterBuiltIn:
                        if inspect.isbuiltin(attr):
                            continue

                    #filter functions?
                    if filterFunction:
                        if inspect.isroutine(attr) or isinstance(attr, MethodWrapperType):
                            continue
                except:
                    #if some error occurs getting it, let's put it to the user.
                    strIO = StringIO.StringIO()
                    traceback.print_exc(file=strIO)
                    attr = strIO.getvalue()

                d[ n ] = attr

        return d


#=======================================================================================================================
# DictResolver
#=======================================================================================================================
class DictResolver:

    def resolve(self, dict, key):
        if key in ('__len__', TOO_LARGE_ATTR):
            return None

        if '(' not in key:
            #we have to treat that because the dict resolver is also used to directly resolve the global and local
            #scopes (which already have the items directly)
            try:
                return dict[key]
            except:
                return getattr(dict, key)

        #ok, we have to iterate over the items to find the one that matches the id, because that's the only way
        #to actually find the reference from the string we have before.
        expected_id = int(key.split('(')[-1][:-1])
        for key, val in dict_iter_items(dict):
            if id(key) == expected_id:
                return val

        raise UnableToResolveVariableException()

    def key_to_str(self, key):
        if isinstance(key, str):
            return '%r' % key
        else:
            if not pydevd_constants.IS_PY3K:
                if isinstance(key, unicode):
                    return "u'%s'" % key
            return key

    def init_dict(self):
        return OrderedDict()

    def get_dictionary(self, dict):
        dict, offset = get_var_and_offset(dict)

        ret = self.init_dict()

        for i, (key, val) in enumerate(dict_iter_items(dict)):
            if i >= offset:
                if i >= offset + MAX_ITEMS_TO_HANDLE:
                    if not IS_PYCHARM:
                        ret[TOO_LARGE_ATTR] = TOO_LARGE_MSG
                    break
                # we need to add the id because otherwise we cannot find the real object to get its contents later on.
                key = '%s (%s)' % (self.key_to_str(key), id(key))
                ret[key] = val

        ret['__len__'] = len(dict)
        # in case if the class extends built-in type and has some additional fields
        additional_fields = defaultResolver.get_dictionary(dict)
        if IS_PYCHARM:
            if offset == 0:
                additional_fields.update(ret)
                ret = additional_fields
        else:
            ret.update(additional_fields)
        return ret


#=======================================================================================================================
# TupleResolver
#=======================================================================================================================
class TupleResolver: #to enumerate tuples and lists

    def resolve(self, var, attribute):
        '''
            @param var: that's the original attribute
            @param attribute: that's the key passed in the dict (as a string)
        '''
        if attribute in ('__len__', TOO_LARGE_ATTR):
            return None
        try:
            return var[int(attribute)]
        except:
            return getattr(var, attribute)

    def get_dictionary(self, var):
        var, offset = get_var_and_offset(var)

        l = len(var)
        d = OrderedDict()

        format_str = '%0' + str(int(len(str(l)))) + 'd'

        i = offset
        for item in var[offset:offset+MAX_ITEMS_TO_HANDLE]:
            d[format_str % i] = item
            i += 1

            if i > MAX_ITEMS_TO_HANDLE + offset:
                if not IS_PYCHARM:
                    d[TOO_LARGE_ATTR] = TOO_LARGE_MSG
                break

        d['__len__'] = len(var)
        # in case if the class extends built-in type and has some additional fields
        additional_fields = defaultResolver.get_dictionary(var)
        if IS_PYCHARM:
            if offset == 0:
                additional_fields.update(d)
                d = additional_fields
        else:
            d.update(additional_fields)
        return d



#=======================================================================================================================
# SetResolver
#=======================================================================================================================
class SetResolver:
    '''
        Resolves a set as dict id(object)->object
    '''

    def resolve(self, var, attribute):
        if attribute in ('__len__', TOO_LARGE_ATTR):
            return None

        try:
            attribute = int(attribute)
        except:
            return getattr(var, attribute)

        for v in var:
            if id(v) == attribute:
                return v

        raise UnableToResolveVariableException('Unable to resolve %s in %s' % (attribute, var))

    def get_dictionary(self, var):
        var, offset = get_var_and_offset(var)

        d = OrderedDict()
        i = 0
        for item in var:
            if i >= offset:
                if i >= offset + MAX_ITEMS_TO_HANDLE:
                    if not IS_PYCHARM:
                        d[TOO_LARGE_ATTR] = TOO_LARGE_MSG
                    break
                d[str(id(item))] = item
            i += 1

        d['__len__'] = len(var)
        # in case if the class extends built-in type and has some additional fields
        additional_fields = defaultResolver.get_dictionary(var)
        if IS_PYCHARM:
            if offset == 0:
                additional_fields.update(d)
                d = additional_fields
        else:
            d.update(additional_fields)
        return d


#=======================================================================================================================
# InstanceResolver
#=======================================================================================================================
class InstanceResolver:

    def resolve(self, var, attribute):
        field = var.__class__.getDeclaredField(attribute)
        field.setAccessible(True)
        return field.get(var)

    def get_dictionary(self, obj):
        ret = {}

        declaredFields = obj.__class__.getDeclaredFields()
        for i in xrange(len(declaredFields)):
            name = declaredFields[i].getName()
            try:
                declaredFields[i].setAccessible(True)
                ret[name] = declaredFields[i].get(obj)
            except:
                traceback.print_exc()

        return ret


#=======================================================================================================================
# JyArrayResolver
#=======================================================================================================================
class JyArrayResolver:
    '''
        This resolves a regular Object[] array from java
    '''

    def resolve(self, var, attribute):
        if attribute == '__len__':
            return None
        return var[int(attribute)]

    def get_dictionary(self, obj):
        ret = {}

        for i in xrange(len(obj)):
            ret[ i ] = obj[i]

        ret['__len__'] = len(obj)
        return ret




#=======================================================================================================================
# MultiValueDictResolver
#=======================================================================================================================
class MultiValueDictResolver(DictResolver):

    def resolve(self, dict, key):
        if key in ('__len__', TOO_LARGE_ATTR):
            return None

        #ok, we have to iterate over the items to find the one that matches the id, because that's the only way
        #to actually find the reference from the string we have before.
        expected_id = int(key.split('(')[-1][:-1])
        for key in dict_keys(dict):
            val = dict.getlist(key)
            if id(key) == expected_id:
                return val

        raise UnableToResolveVariableException()



#=======================================================================================================================
# DjangoFormResolver
#=======================================================================================================================
class DjangoFormResolver(DefaultResolver):
    has_errors_attr = False

    def get_names(self, var):
        names = dir(var)
        if not names and hasattr(var, '__members__'):
            names = var.__members__

        if "errors" in names:
            self.has_errors_attr = True
            names.remove("errors")
        return names

    def get_dictionary(self, var, names=None):
        # Do not call self.errors because it is property and has side effects
        d = defaultResolver.get_dictionary(var, self.get_names(var))
        if self.has_errors_attr:
            try:
                errors_attr = getattr(var, "_errors")
            except:
                errors_attr = None
            d["errors"] = errors_attr
        return d


#=======================================================================================================================
# DequeResolver
#=======================================================================================================================
class DequeResolver(TupleResolver):
    def get_dictionary(self, var):
        var, offset = get_var_and_offset(var)

        l = len(var)
        d = OrderedDict()

        format_str = '%0' + str(int(len(str(l)))) + 'd'

        i = 0
        for item in var:
            if i >= offset:
                if i >= offset + MAX_ITEMS_TO_HANDLE:
                    if not IS_PYCHARM:
                        d[TOO_LARGE_ATTR] = TOO_LARGE_MSG
                    break
                d[format_str % i] = item
            i += 1

        d['__len__'] = len(var)
        # in case if the class extends built-in type and has some additional fields
        additional_fields = defaultResolver.get_dictionary(var)
        if IS_PYCHARM:
            if offset == 0:
                additional_fields['maxlen'] = getattr(var, 'maxlen', None)
                additional_fields.update(d)
                d = additional_fields
        else:
            d.update(additional_fields)
        return d


#=======================================================================================================================
# OrderedDictResolver
#=======================================================================================================================
class OrderedDictResolver(DictResolver):
    def init_dict(self):
        return OrderedDict()


#=======================================================================================================================
# FrameResolver
#=======================================================================================================================
class FrameResolver:
    '''
    This resolves a frame.
    '''

    def resolve(self, obj, attribute):
        if attribute == '__internals__':
            return defaultResolver.get_dictionary(obj)

        if attribute == 'stack':
            return self.get_frame_stack(obj)

        if attribute == 'f_locals':
            return obj.f_locals

        return None


    def get_dictionary(self, obj):
        ret = {}
        ret['__internals__'] = defaultResolver.get_dictionary(obj)
        ret['stack'] = self.get_frame_stack(obj)
        ret['f_locals'] = obj.f_locals
        return ret


    def get_frame_stack(self, frame):
        ret = []
        if frame is not None:
            ret.append(self.get_frame_name(frame))

            while frame.f_back:
                frame = frame.f_back
                ret.append(self.get_frame_name(frame))

        return ret

    def get_frame_name(self, frame):
        if frame is None:
            return 'None'
        try:
            name = basename(frame.f_code.co_filename)
            return 'frame: %s [%s:%s]  id:%s' % (frame.f_code.co_name, name, frame.f_lineno, id(frame))
        except:
            return 'frame object'


defaultResolver = DefaultResolver()
dictResolver = DictResolver()
tupleResolver = TupleResolver()
instanceResolver = InstanceResolver()
jyArrayResolver = JyArrayResolver()
setResolver = SetResolver()
multiValueDictResolver = MultiValueDictResolver()
djangoFormResolver = DjangoFormResolver()
dequeResolver = DequeResolver()
orderedDictResolver = OrderedDictResolver()
frameResolver = FrameResolver()
