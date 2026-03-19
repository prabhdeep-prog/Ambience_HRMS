# Horilla Settings V2 - Complete Implementation Guide

## Overview

This guide covers the migration from the old cluttered settings interface to a modern, enterprise-grade settings management system.

---

## 📁 File Structure

```
horilla/
├── templates/
│   ├── settings_v2_refactored.html          ← Main settings layout
│   └── settings_example_company.html        ← Example form implementation
│
├── base/
│   ├── static/
│   │   ├── css/
│   │   │   └── settings_v2.css              ← All styling (730+ lines)
│   │   └── js/
│   │       └── settings_v2.js               ← Change detection & form management
│   │
│   ├── forms/
│   │   └── settings_forms.py                ← Form base classes & mixins
│   │
│   └── static/docs/
│       ├── SETTINGS_REDESIGN_ARCHITECTURE.md
│       └── SETTINGS_IMPLEMENTATION_GUIDE.md (this file)
```

---

## 🚀 Quick Start

### Step 1: Create Your Settings Form

```python
# base/forms/settings_forms.py
from base.forms.settings_forms import BaseSettingsForm
from django import forms

class MySettingsForm(BaseSettingsForm):
    """My custom settings form."""

    setting_name = forms.CharField(
        label="Setting Name",
        help_text="Description of this setting",
        required=True,
    )

    setting_choice = forms.ChoiceField(
        label="Choose Option",
        choices=[
            ('option1', 'First Option'),
            ('option2', 'Second Option'),
        ],
        help_text="Help text appears below the field",
    )

    # Automatic features:
    # ✅ CSS classes added automatically
    # ✅ ARIA labels for accessibility
    # ✅ Required field indicators
    # ✅ Help text display
    # ✅ Focus states
    # ✅ Error handling
```

### Step 2: Create Your Settings Template

```html
{% extends 'settings_v2_refactored.html' %}
{% load i18n %}

{% block settings %}
<div class="oh-settings-form">

  {# Header #}
  <div class="oh-settings-form__header">
    <h2 class="oh-settings-form__title">My Settings</h2>
    <p class="oh-settings-form__description">Configure my settings here</p>
  </div>

  {# Form #}
  <form method="post">
    {% csrf_token %}

    {# Form Group (Section) #}
    <div class="oh-form-group">
      <h3 class="oh-form-group__title">Basic Settings</h3>
      <p class="oh-form-group__description">Settings for basic functionality</p>

      <div class="oh-form-row oh-form-row--two">
        {# Field 1 #}
        <div class="oh-form-field {% if form.setting_name.errors %}oh-has-error{% endif %}">
          <label for="{{ form.setting_name.id_for_label }}" class="oh-form-field__label">
            Setting Name <span class="oh-form-field__label-required">*</span>
          </label>
          {{ form.setting_name }}
          {% if form.setting_name.help_text %}
          <p class="oh-form-field__help">{{ form.setting_name.help_text|safe }}</p>
          {% endif %}
          {% if form.setting_name.errors %}
          <div class="oh-form-field__error">{{ form.setting_name.errors|join:", " }}</div>
          {% endif %}
        </div>

        {# Field 2 #}
        <div class="oh-form-field {% if form.setting_choice.errors %}oh-has-error{% endif %}">
          <label for="{{ form.setting_choice.id_for_label }}" class="oh-form-field__label">
            Setting Choice
          </label>
          {{ form.setting_choice }}
          {% if form.setting_choice.help_text %}
          <p class="oh-form-field__help">{{ form.setting_choice.help_text|safe }}</p>
          {% endif %}
        </div>
      </div>
    </div>

    {# Form Actions #}
    <div class="oh-form-actions">
      <button type="button" class="oh-btn oh-btn--secondary" onclick="document.forms[0].reset()">
        Reset
      </button>
      <button type="submit" class="oh-btn oh-btn--primary">
        Save Changes
      </button>
    </div>
  </form>

</div>
{% endblock %}
```

### Step 3: Create Your Settings View

```python
# myapp/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from base.forms.settings_forms import MySettingsForm

@login_required
def my_settings_view(request):
    if request.method == 'POST':
        form = MySettingsForm(request.POST)
        if form.is_valid():
            # Handle form submission
            # Save settings, update config, etc.
            pass
    else:
        # Load existing settings
        form = MySettingsForm()

    return render(request, 'settings_example_company.html', {'form': form})
```

### Step 4: Add URL Pattern

```python
# myapp/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('settings/my-settings/', views.my_settings_view, name='my-settings'),
]
```

---

## 📐 CSS Classes Reference

### Layout Classes

```html
<!-- Main container -->
<div class="oh-settings-container">
  <aside class="oh-settings-sidebar">...</aside>
  <main class="oh-settings-content">...</main>
</div>

<!-- Form groups (sections) -->
<div class="oh-form-group">
  <h3 class="oh-form-group__title">Title</h3>
  <p class="oh-form-group__description">Description</p>
</div>

<!-- Form rows (responsive grid) -->
<div class="oh-form-row">                  <!-- Auto 1-3 columns -->
<div class="oh-form-row oh-form-row--full"> <!-- 1 column -->
<div class="oh-form-row oh-form-row--two">  <!-- 2 columns -->
```

### Field Classes

```html
<!-- Form field container -->
<div class="oh-form-field {% if form.field.errors %}oh-has-error{% endif %}">

  <!-- Label (auto styles) -->
  <label class="oh-form-field__label">
    Label Text
    <span class="oh-form-field__label-required">*</span>
  </label>

  <!-- Input (auto styled by BaseSettingsForm) -->
  {{ form.field }}  {# Gets .oh-form-field__input class automatically #}

  <!-- Help text -->
  <p class="oh-form-field__help">Helper text</p>

  <!-- Error message -->
  <div class="oh-form-field__error">Error message</div>
</div>
```

### Button Classes

```html
<!-- Primary (blue) -->
<button class="oh-btn oh-btn--primary">Save</button>

<!-- Secondary (gray) -->
<button class="oh-btn oh-btn--secondary">Cancel</button>

<!-- Text (link-like) -->
<button class="oh-btn oh-btn--text">Learn More</button>

<!-- Danger (red) -->
<button class="oh-btn oh-btn--danger">Delete</button>

<!-- With icon -->
<button class="oh-btn oh-btn--primary">
  <ion-icon name="checkmark-outline"></ion-icon>
  Save Changes
</button>
```

### Danger Zone

```html
<div class="oh-danger-zone">
  <div class="oh-danger-zone__header">
    <ion-icon name="warning-outline" class="oh-danger-zone__icon"></ion-icon>
    <h3 class="oh-danger-zone__title">Danger Zone</h3>
  </div>
  <p class="oh-danger-zone__description">Warning text</p>
  <div class="oh-danger-zone__action">
    <button class="oh-btn oh-btn--danger oh-danger-zone__button">Delete</button>
  </div>
</div>
```

---

## 🎨 Design System

### Color Palette (CSS Variables)

```css
--oh-color-primary: #3B82F6           /* Blue */
--oh-color-danger: #EF4444           /* Red */
--oh-color-success: #10B981          /* Green */
--oh-color-warning: #F59E0B          /* Orange */

--oh-color-text-primary: #1F2937     /* Dark Gray */
--oh-color-text-secondary: #6B7280   /* Medium Gray */
--oh-color-text-tertiary: #9CA3AF    /* Light Gray */

--oh-color-bg-white: #FFFFFF
--oh-color-bg-light: #F9FAFB
--oh-color-bg-lighter: #F3F4F6

--oh-color-border: #E5E7EB
```

### Spacing (8px base unit)

```css
--oh-space-xs: 4px
--oh-space-sm: 8px
--oh-space-md: 12px
--oh-space-lg: 16px
--oh-space-xl: 24px
--oh-space-2xl: 32px
--oh-space-3xl: 48px
```

### Breakpoints

- **Mobile**: < 640px
- **Tablet**: 640px - 1024px
- **Desktop**: > 1024px

---

## ✨ Features

### 1. Change Detection

The system automatically tracks form changes and shows a sticky save bar:

```javascript
// Automatic on all forms inside oh-settings-page
// Shows when user makes changes
// Hides when user saves or discards
```

### 2. Responsive Design

- **Desktop**: Full sidebar + content area
- **Tablet**: Sidebar as grid
- **Mobile**: Collapsible drawer navigation

### 3. Accessibility

- ✅ WCAG 2.1 AA compliant
- ✅ ARIA labels on all inputs
- ✅ Keyboard navigation
- ✅ Focus indicators
- ✅ Help text linked to inputs

### 4. Form Validation

```python
class MyForm(BaseSettingsForm):
    email = forms.EmailField(help_text="Your email address")

    # Errors automatically styled:
    # - Red border on input
    # - Red background
    # - Red error message below field
```

### 5. Search Navigation

Users can search settings in the sidebar:

```html
<input type="text" id="settingsSearch" placeholder="Search settings..." />
<!-- Automatically filters sidebar items as user types -->
```

---

## 📊 State Management

### Form State Tracking

```javascript
// Automatic via SettingsPageManager
// Tracks initial form state on page load
// Compares current state to initial on each input
// Shows/hides save bar based on changes

// Debounced at 300ms for performance
// Prevents "beforeunload" warning if user saved
```

### Unsaved Changes Protection

```javascript
// If user tries to navigate away with unsaved changes:
// 1. Prevents navigation
// 2. Shows confirmation dialog
// 3. Allows user to save or discard before leaving
```

---

## 🔐 Security Considerations

### 1. CSRF Protection

All forms automatically include `{% csrf_token %}`:

```html
<form method="post">
  {% csrf_token %}  {# Automatic CSRF protection #}
  ...
</form>
```

### 2. XSS Prevention

- Form fields auto-escaped
- Help text marked as safe only if from trusted sources
- Use `|safe` filter carefully

### 3. Input Validation

```python
class MyForm(BaseSettingsForm):
    # Django's built-in validators work automatically
    email = forms.EmailField()  # Validates email format
    phone = forms.CharField(max_length=20)  # Max length enforced

    # Add custom validation
    def clean_phone(self):
        phone = self.cleaned_data['phone']
        if not phone.replace('-', '').isdigit():
            raise forms.ValidationError('Invalid phone format')
        return phone
```

---

## 🛠 Advanced Usage

### Custom Form Mixin

```python
class MyCustomMixin(SettingsFormMixin):
    """Add custom behavior to settings forms."""

    def get_initial_data(self):
        """Load initial data from database or cache."""
        return {
            'company_name': get_company_name(),
        }

    def handle_post_save(self):
        """Run custom logic after form saves."""
        clear_settings_cache()
        send_audit_log('settings_changed')
```

### Dynamic Form Fields

```python
class DynamicSettingsForm(BaseSettingsForm):
    def __init__(self, company_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dynamically add fields based on context
        if company_id:
            company = Company.objects.get(id=company_id)
            if company.tier == 'enterprise':
                self.fields['sso_enabled'] = forms.BooleanField()
                self.fields['api_key'] = forms.CharField()
```

### Template Filtering

```python
# In settings_forms.py
def get_form_field_attributes(form, field_name):
    """Get all attributes needed to render field."""
    field = form[field_name]
    return {
        'field': field,
        'label': field.label,
        'help_text': field.help_text,
        'errors': field.errors,
        'required': field.field.required,
        'widget_type': field.field.widget.__class__.__name__,
    }
```

---

## 📱 Mobile Responsiveness

### Automatic on All Views

```css
/* Tablet (640px - 1024px) */
@media (max-width: 1024px) {
  .oh-settings-container {
    flex-direction: column;  /* Stack vertically */
  }
  .oh-settings-sidebar {
    display: grid;  /* Multi-column layout */
  }
}

/* Mobile (< 640px) */
@media (max-width: 640px) {
  .oh-settings-sidebar {
    position: fixed;  /* Drawer navigation */
    left: -100%;
    transition: left 300ms ease;
  }
}
```

### Touch-Friendly

- Buttons: 44px minimum height
- Touch targets: 8px padding minimum
- Readable font: 14px minimum on mobile

---

## 🧪 Testing

### Test Form Styling

```python
from django.test import TestCase
from django.forms import CharField

class TestSettingsForm(TestCase):
    def test_form_fields_have_css_classes(self):
        form = MySettingsForm()

        # Check that CSS classes were added
        for field in form.fields.values():
            self.assertIn('oh-form-field__input',
                         field.widget.attrs.get('class', ''))

    def test_form_fields_have_aria_labels(self):
        form = MySettingsForm()

        for field_name, field in form.fields.items():
            self.assertIn('aria-label', field.widget.attrs)
```

### Test Change Detection

```python
# Automatic via JavaScript in browser
# Use Selenium for E2E testing
from selenium import webdriver

def test_unsaved_changes_warning():
    driver = webdriver.Chrome()
    driver.get('/settings/my-settings/')

    # Fill form
    driver.find_element('name', 'company_name').send_keys('New Name')

    # Try to navigate away
    driver.get('/dashboard/')

    # Should show warning
    alert = driver.switch_to.alert
    assert 'unsaved changes' in alert.text.lower()
```

---

## 🚨 Troubleshooting

### Issue: Form fields not styled

**Solution:**
```python
class MyForm(BaseSettingsForm):  # Must inherit from BaseSettingsForm
    # Not Form or ModelForm directly
```

### Issue: Save bar not appearing

**Solution:**
```html
<!-- Make sure form has name attribute -->
<form method="post" name="settingsForm">
  {% csrf_token %}
</form>
```

### Issue: Mobile sidebar not collapsible

**Solution:**
```html
<!-- Make sure settings_v2.js is loaded -->
<script src="{% static 'js/settings_v2.js' %}"></script>
```

### Issue: CSS variables not working

**Solution:**
```css
/* Make sure :root variables are defined in settings_v2.css */
/* Use fallback colors if needed */
color: var(--oh-color-primary, #3B82F6);
```

---

## 📈 Performance Optimization

### 1. Debounced Change Detection

```javascript
// Already implemented in SettingsPageManager
debounce(fn, delay) {  // 300ms delay
  // Prevents excessive function calls
  // Improves performance on large forms
}
```

### 2. Lazy Load Secondary Navigation

```python
# In view
secondary_items = get_secondary_nav()  # Load on demand
```

### 3. CSS Minification

```bash
# Minify settings_v2.css for production
csso settings_v2.css -o settings_v2.min.css
```

### 4. JavaScript Bundle

```bash
# Combine scripts for single request
uglifyjs settings_v2.js -o settings_v2.min.js
```

---

## 🔄 Migration from Old Settings

### Step 1: Update Templates

Old:
```html
<div class="oh-card">
  <div class="row">
    <div class="col-lg-3">...</div>
    <div class="col-lg-9">{% block settings %}...{% endblock %}</div>
  </div>
</div>
```

New:
```html
{% extends 'settings_v2_refactored.html' %}
{% block settings %}...{% endblock %}
```

### Step 2: Update Forms

Old:
```python
class MyForm(forms.Form):
    field = forms.CharField()
```

New:
```python
class MyForm(BaseSettingsForm):
    field = forms.CharField(help_text="Description")
```

### Step 3: Update URL Config

```python
# In settings.html sidebar, update href
<a href="{% url 'my-new-settings' %}">...</a>
```

---

## 📚 Resources

- **Design System**: `/base/static/docs/SETTINGS_REDESIGN_ARCHITECTURE.md`
- **CSS Reference**: `/base/static/css/settings_v2.css`
- **JavaScript**: `/base/static/js/settings_v2.js`
- **Forms**: `/base/forms/settings_forms.py`

---

## ✅ Checklist for New Settings Page

- [ ] Created form inheriting from `BaseSettingsForm`
- [ ] Created template extending `settings_v2_refactored.html`
- [ ] Added form fields with `help_text`
- [ ] Used `.oh-form-group` for sections
- [ ] Used `.oh-form-row` for responsive layout
- [ ] Added `.oh-form-field` wrappers for each field
- [ ] Included `.oh-form-actions` with buttons
- [ ] Added danger zone if applicable
- [ ] Tested on mobile/tablet/desktop
- [ ] Verified WCAG accessibility
- [ ] Added success/error notifications
- [ ] Tested unsaved changes warning
- [ ] Documented help text for users

---

**Last Updated**: March 2026
**Version**: 2.0
**Status**: Production Ready
