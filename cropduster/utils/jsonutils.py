from jsonutil import jsonutil
from cropduster.resizing import Size


def json_default(obj):
    if callable(getattr(obj, '__serialize__', None)):
        dct = obj.__serialize__()
        module = obj.__module__
        if module == '__builtin__':
            module = None
        if isinstance(obj, type):
            name = obj.__name__
        else:
            name = obj.__class__.__name__
        type_name = u'.'.join(filter(None, [module, name]))
        dct.update({'__type__': type_name})
        return dct
    raise TypeError("object of type %s is not JSON serializable" % type(obj).__name__)


def object_hook(dct):
    if dct.get('__type__') == 'cropduster.resizing.Size':
        return Size(
            name=dct.get('name'),
            w=dct.get('w'),
            h=dct.get('h'),
            min_w=dct.get('min_w'),
            min_h=dct.get('min_h'),
            retina=dct.get('retina'),
            auto=dct.get('auto'))
    return dct


def dumps(obj, *args, **kwargs):
    kwargs.setdefault('default', json_default)
    return jsonutil.dumps(obj, *args, **kwargs)


def loads(s, *args, **kwargs):
    kwargs.setdefault('object_hook', object_hook)
    return jsonutil.loads(s, *args, **kwargs)