import os
import re

from django.conf import settings
from cropduster.settings import *

from django import forms
from django.forms.models import ModelMultipleChoiceField
from django.core.exceptions import ValidationError

from django.forms.widgets import Input

from django.template.loader import render_to_string

from django.contrib.contenttypes.generic import BaseGenericInlineFormSet, generic_inlineformset_factory

from cropduster.models import Image, Thumb
from cropduster.utils import get_aspect_ratios, validate_sizes, OrderedDict, get_min_size

from jsonutil import jsonutil

class CropDusterWidget(Input):
	class Media:
		css = {
			'all': (os.path.join(CROPDUSTER_MEDIA_URL, 'css/CropDuster.css'), )
		}
		js = (os.path.join(CROPDUSTER_MEDIA_URL, 'js/CropDuster.js'), )
	
	def __init__(self, sizes=None, auto_sizes=None, default_thumb=None, attrs=None):
		self.sizes = sizes
		self.auto_sizes = auto_sizes
		self.default_thumb = default_thumb
		self.formset = generic_inlineformset_factory(Image)

		if attrs is not None:
			self.attrs = attrs.copy()
		else:
			self.attrs = {}
	
	def render(self, name, value, attrs=None):
		from jsonutil import jsonutil as json
		import simplejson
		
		final_attrs = self.build_attrs(attrs, type=self.input_type, name=name)
	
		self.value = value
		thumbs = OrderedDict({})

		if value is None or value == "":
			has_value = False
			final_attrs['value'] = ""
			display_value = ""

		else:
			has_value = True		
			final_attrs['value'] = value
			image = Image.objects.get(pk=value)
			for thumb in image.thumbs.order_by('-width').all():
				size_name = thumb.name
				thumbs[size_name] = image.get_image_url(size_name)

		final_attrs['upload_icon'] = os.path.join(
			CROPDUSTER_MEDIA_URL,
			'img/cropduster_icon_upload_select.png'
		)
		final_attrs['sizes'] = simplejson.dumps(self.sizes)
		final_attrs['auto_sizes'] = simplejson.dumps(self.auto_sizes)
	
		if self.default_thumb is not None:
			default_thumb = self.default_thumb
		else:
			default_thumb = ''
	
		aspect_ratios = get_aspect_ratios(self.sizes)
		aspect_ratio = json.dumps(aspect_ratios[0])
		min_size = json.dumps(get_min_size(self.sizes, self.auto_sizes))
		# id and name prefix for form fields
		formset = self.formset
		inline_admin_formset = self.formset
		prefix = self.formset.get_default_prefix()
		static_url = simplejson.dumps(settings.STATIC_URL)
		return render_to_string("cropduster/custom_field.html", locals())


class CropDusterFormField(forms.IntegerField):
	
	def __init__(self, sizes=None, auto_sizes=None, default_thumb=None, *args, **kwargs):
		if default_thumb is None:
			raise ValueError("default_thumb attribute must be defined.")
		
		default_thumb_key_exists = False
		
		try:
			self._sizes_validate(sizes)
			if default_thumb in sizes.keys():
				default_thumb_key_exists = True
		except ValueError as e:
			# Maybe the sizes is none and the auto_sizes is valid, let's
			# try that
			try:
				self._sizes_validate(auto_sizes, is_auto=True)
			except:
				# raise the original exception
				raise e
		
		if auto_sizes is not None:
			self._sizes_validate(auto_sizes, is_auto=True)
			if default_thumb in auto_sizes.keys():
				default_thumb_key_exists = True
		
		if not default_thumb_key_exists:
			raise ValueError("default_thumb attribute does not exist in either sizes or auto_sizes dict.")
		
		self.sizes = sizes
		self.auto_sizes = auto_sizes
		self.default_thumb = default_thumb
		
		widget = CropDusterWidget(sizes=sizes, auto_sizes=auto_sizes, default_thumb=default_thumb)
		kwargs['widget'] = widget
		super(CropDusterFormField, self).__init__(*args, **kwargs)
	
	def _sizes_validate(self, sizes, is_auto=False):
		validate_sizes(sizes)	
		if not is_auto:
			aspect_ratios = get_aspect_ratios(sizes)
			if len(aspect_ratios) > 1:
				raise ValueError("More than one aspect ratio: %s" % jsonutil.dumps(aspect_ratios))

class CropDusterThumbField(ModelMultipleChoiceField):
	def clean(self, value):
		"""
		Override default validation so that it doesn't throw a ValidationError
		if a given value is not in the original queryset.
		"""
		required_msg = self.error_messages['required']
		list_msg = self.error_messages['list']
		ret = value
		try:
			ret = super(CropDusterThumbField, self).clean(value)
		except ValidationError, e:
			if required_msg in e.messages or list_msg in e.messages:
				raise e
		return ret


class BaseInlineFormset(BaseGenericInlineFormSet):
	sizes = None
	auto_sizes = None
	default_thumb = None

	def _construct_form(self, i, **kwargs):
		"""
		Override the id field of the form with our CropDusterFormField and
		override the thumbs queryset for performance.
		"""
		
		image_id = 0
		try:
			image_id = self.queryset[0].id
		except:
			pass
		
		# Limit the queryset for performance reasons
		try:
			queryset = Image.objects.get(pk=image_id).thumbs.get_query_set()
			self.form.base_fields['thumbs'].queryset = queryset
			self.form.base_fields['thumbs'].widget.widget.choices.queryset = queryset
		except Image.DoesNotExist:
			if self.data is not None and len(self.data) > 0:
				thumb_ids = [int(id) for id in self.data.getlist(self.rel_name + '-0-thumbs')]
				queryset = Thumb.objects.filter(pk__in=thumb_ids)
				self.form.base_fields['thumbs'].queryset = queryset
				self.form.base_fields['thumbs'].widget.widget.choices.queryset = queryset
			else:
				# Return an empty queryset
				queryset = Thumb.objects.filter(pk=0)
				self.form.base_fields['thumbs'].queryset = queryset
				self.form.base_fields['thumbs'].widget.widget.choices.queryset = queryset
		
		if self.data is not None and len(self.data) > 0:
			pk_key = "%s-%s" % (self.add_prefix(i), self.model._meta.pk.name)
			pk = self.data[pk_key]
			if pk == '' and image_id != 0:
				self.data[pk_key] = image_id

			if self.data.get(self.rel_name + '-0-id') == '':
				img_kwargs = {}
				for field_name in self.form.base_fields:
					if field_name not in ('DELETE', 'id', 'thumbs'):
						img_kwargs[field_name] = self.data.get('%s-%s' % (self.add_prefix(i), field_name))
						if field_name in ('crop_x', 'crop_y', 'crop_w', 'crop_h'):
							img_kwargs[field_name] = int(img_kwargs[field_name])
				try:
					if image_id != 0:
						img = Image.objects.get(pk=image_id)
						# If cache machine exists, invalidate
					else:
						img = Image(**img_kwargs)
					self.form.instance = img
					try:
						Image.objects.invalidate(img)
					except:
						pass
					try:
						# Invalidate parent instance
						self.instance.__class__.objects.invalidate(self.instance)
					except:
						pass
				except Exception, e:
					pass

		form = super(BaseInlineFormset, self)._construct_form(i, **kwargs)
		
		# Override the id field to use our custom field and widget that displays the
		# thumbnail and the button that pops up the cropduster window
		form.fields['id'] = CropDusterFormField(
			label="Upload",
			sizes = self.sizes,
			auto_sizes = self.auto_sizes,
			default_thumb=self.default_thumb,
			required=False
		)
		
		# Load in initial data if we have it from a previously submitted
		# (but apparently invalidated) form
		if self.data is not None and len(self.data) > 0:
			thumb_ids = [int(id) for id in self.data.getlist(self.rel_name + '-0-thumbs')]
			if len(thumb_ids) > 0:
				for key in self.data.keys():
					if key.find(self.rel_name) == 0:
						match = re.match(self.rel_name + '-(.+)$', key)
						if match:
							field_name = match.group(1)
							if field_name in form.fields:
								field = form.fields[field_name]
								field.initial = self.data.get(key)
		return form

