/**
 * Horilla Settings V2 - Change Detection & Form Management
 * Handles form state tracking, save bar visibility, and user interactions
 */

class SettingsPageManager {
  constructor(options = {}) {
    this.options = {
      sidebarSelector: '.oh-settings-sidebar',
      contentSelector: '.oh-settings-content',
      saveBarSelector: '#settingsSaveBar',
      formSelector: 'form',
      searchSelector: '#settingsSearch',
      debounceDelay: 300,
      ...options,
    };

    // State tracking
    this.initialFormState = new Map();
    this.hasUnsavedChanges = false;
    this.pendingSave = false;

    // DOM elements
    this.elements = {
      sidebar: document.querySelector(this.options.sidebarSelector),
      content: document.querySelector(this.options.contentSelector),
      saveBar: document.querySelector(this.options.saveBarSelector),
      saveBtn: document.getElementById('saveChangesBtn'),
      discardBtn: document.getElementById('discardChangesBtn'),
      searchInput: document.querySelector(this.options.searchSelector),
    };

    this.init();
  }

  /**
   * Initialize the settings page
   */
  init() {
    this.setupEventListeners();
    this.setupFormTracking();
    this.setupNavigation();
    this.restoreLastActiveTab();
  }

  /**
   * Setup event listeners
   */
  setupEventListeners() {
    // Save and discard buttons
    if (this.elements.saveBtn) {
      this.elements.saveBtn.addEventListener('click', () => this.handleSave());
    }
    if (this.elements.discardBtn) {
      this.elements.discardBtn.addEventListener(
        'click',
        () => this.handleDiscard()
      );
    }

    // Prevent unsaved changes warning on navigation
    window.addEventListener('beforeunload', (e) => {
      if (this.hasUnsavedChanges && !this.pendingSave) {
        e.preventDefault();
        e.returnValue = '';
      }
    });

    // Search functionality
    if (this.elements.searchInput) {
      this.setupSearch();
    }

    // Sidebar navigation
    this.setupSidebarNavigation();
  }

  /**
   * Setup form state tracking
   */
  setupFormTracking() {
    const form = document.querySelector(this.options.formSelector);
    if (!form) return;

    // Store initial state
    this.captureFormState(form);

    // Track all input changes
    const inputs = form.querySelectorAll(
      'input:not([type="hidden"]), textarea, select'
    );

    inputs.forEach((input) => {
      // Track on input (with debounce)
      input.addEventListener('input', () => this.debounce(() => this.checkForChanges(form), this.options.debounceDelay)());

      // Track on change (select, checkbox, radio)
      input.addEventListener('change', () => this.checkForChanges(form));

      // Form submission
      form.addEventListener('submit', (e) => this.handleFormSubmit(e, form));
    });
  }

  /**
   * Capture current form state
   */
  captureFormState(form) {
    const formData = new FormData(form);
    this.initialFormState = new Map(formData);
  }

  /**
   * Check if form has unsaved changes
   */
  checkForChanges(form) {
    const currentFormData = new FormData(form);
    let hasChanges = false;

    // Compare current state with initial state
    for (let [key, value] of currentFormData) {
      if (!this.initialFormState.has(key) || this.initialFormState.get(key) !== value) {
        hasChanges = true;
        break;
      }
    }

    // Check for removed fields
    if (!hasChanges) {
      for (let key of this.initialFormState.keys()) {
        if (!currentFormData.has(key)) {
          hasChanges = true;
          break;
        }
      }
    }

    this.setUnsavedChanges(hasChanges);
  }

  /**
   * Set unsaved changes state and update UI
   */
  setUnsavedChanges(hasChanges) {
    this.hasUnsavedChanges = hasChanges;
    this.updateSaveBar();
  }

  /**
   * Update save bar visibility
   */
  updateSaveBar() {
    if (!this.elements.saveBar) return;

    if (this.hasUnsavedChanges) {
      this.elements.saveBar.classList.add('oh-settings-save-bar--visible');
      this.elements.saveBar.classList.remove('oh-settings-save-bar--hidden');
      this.showNotification(
        'Changes detected',
        'info',
        2000
      );
    } else {
      this.elements.saveBar.classList.remove('oh-settings-save-bar--visible');
      this.elements.saveBar.classList.add('oh-settings-save-bar--hidden');
    }
  }

  /**
   * Handle save action
   */
  async handleSave() {
    const form = document.querySelector(this.options.formSelector);
    if (!form) return;

    this.pendingSave = true;
    this.elements.saveBtn.disabled = true;
    this.elements.saveBtn.innerHTML =
      '<ion-icon name="hourglass-outline"></ion-icon> Saving...';

    try {
      // Submit form via AJAX or standard form submission
      await this.submitForm(form);

      // Update initial state
      this.captureFormState(form);
      this.setUnsavedChanges(false);

      this.showNotification(
        'Settings saved successfully!',
        'success',
        3000
      );
    } catch (error) {
      console.error('Save error:', error);
      this.showNotification(
        'Error saving settings. Please try again.',
        'error',
        3000
      );
    } finally {
      this.pendingSave = false;
      this.elements.saveBtn.disabled = false;
      this.elements.saveBtn.innerHTML =
        '<ion-icon name="checkmark-outline"></ion-icon> Save Changes';
    }
  }

  /**
   * Handle discard action
   */
  handleDiscard() {
    const form = document.querySelector(this.options.formSelector);
    if (!form) return;

    // Reset form to initial state
    form.reset();
    this.captureFormState(form);
    this.setUnsavedChanges(false);

    this.showNotification('Changes discarded', 'info', 2000);
  }

  /**
   * Submit form (can be overridden for custom logic)
   */
  async submitForm(form) {
    return new Promise((resolve, reject) => {
      // For now, use standard form submission
      // In production, use fetch API for better UX
      const xhr = new XMLHttpRequest();
      const formData = new FormData(form);

      xhr.open(form.method, form.action, true);
      xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

      // Handle response
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(xhr.response);
        } else {
          reject(new Error(`HTTP ${xhr.status}`));
        }
      };

      xhr.onerror = () => reject(new Error('Network error'));

      xhr.send(formData);
    });
  }

  /**
   * Handle form submission
   */
  handleFormSubmit(event, form) {
    // Allow normal form submission
    // But mark as pending to prevent beforeunload warning
    this.pendingSave = true;
  }

  /**
   * Setup sidebar navigation
   */
  setupSidebarNavigation() {
    if (!this.elements.sidebar) return;

    const links = this.elements.sidebar.querySelectorAll('.oh-settings-nav__link');
    const sectionToggles = this.elements.sidebar.querySelectorAll(
      '.oh-settings-nav__section-toggle'
    );

    // Navigation link clicks
    links.forEach((link) => {
      link.addEventListener('click', (e) => {
        // Check for unsaved changes before navigation
        if (this.hasUnsavedChanges) {
          e.preventDefault();
          this.showConfirmDialog(
            'Unsaved Changes',
            'You have unsaved changes. Are you sure you want to leave?',
            () => {
              this.hasUnsavedChanges = false;
              window.location.href = link.href;
            }
          );
        }

        // Update active state
        this.setActiveLink(link);
        this.saveLastActiveTab(link.href);
      });
    });

    // Section toggle functionality
    sectionToggles.forEach((toggle) => {
      toggle.addEventListener('click', (e) => {
        e.preventDefault();
        const section = toggle.closest('.oh-settings-nav__section');
        const items = section.querySelector('.oh-settings-nav__items');

        if (items) {
          items.classList.toggle('oh-settings-nav__items--open');
          const icon = toggle.querySelector('ion-icon');
          if (icon) {
            icon.name = items.classList.contains('oh-settings-nav__items--open')
              ? 'chevron-down-outline'
              : 'chevron-right-outline';
          }
        }
      });
    });
  }

  /**
   * Set active link in sidebar
   */
  setActiveLink(link) {
    // Remove active from all links
    const links = this.elements.sidebar.querySelectorAll('.oh-settings-nav__link');
    links.forEach((l) => l.classList.remove('oh-active'));

    // Add active to current link
    link.classList.add('oh-active');

    // Scroll link into view
    link.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /**
   * Restore last active tab from localStorage
   */
  restoreLastActiveTab() {
    const lastTab = localStorage.getItem('horilla_settings_last_tab');
    const currentPath = window.location.pathname;

    if (lastTab && lastTab === currentPath) {
      const link = this.elements.sidebar?.querySelector(
        `.oh-settings-nav__link[href="${currentPath}"]`
      );
      if (link) {
        this.setActiveLink(link);
      }
    } else {
      // Set first available link as active
      const firstLink = this.elements.sidebar?.querySelector('.oh-settings-nav__link');
      if (firstLink) {
        this.setActiveLink(firstLink);
      }
    }
  }

  /**
   * Save last active tab to localStorage
   */
  saveLastActiveTab(path) {
    localStorage.setItem('horilla_settings_last_tab', path);
  }

  /**
   * Setup search functionality
   */
  setupSearch() {
    let searchTimeout;

    this.elements.searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      const query = e.target.value.toLowerCase();

      searchTimeout = setTimeout(() => {
        this.filterNavigationItems(query);
      }, 200);
    });
  }

  /**
   * Filter navigation items by search query
   */
  filterNavigationItems(query) {
    if (!this.elements.sidebar) return;

    const links = this.elements.sidebar.querySelectorAll('.oh-settings-nav__link');
    const sections = this.elements.sidebar.querySelectorAll('.oh-settings-nav__section');

    links.forEach((link) => {
      const text = link.textContent.toLowerCase();
      const matches = text.includes(query);

      if (query === '') {
        link.style.display = '';
        link.classList.remove('oh-hidden');
      } else {
        link.style.display = matches ? '' : 'none';
      }
    });

    // Show/hide sections based on visible items
    sections.forEach((section) => {
      const visibleItems = Array.from(
        section.querySelectorAll('.oh-settings-nav__link')
      ).filter((link) => link.style.display !== 'none');

      section.style.display = visibleItems.length > 0 ? '' : 'none';
    });
  }

  /**
   * Show notification toast
   */
  showNotification(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `oh-notification oh-notification--${type}`;
    toast.textContent = message;

    document.body.appendChild(toast);

    // Trigger animation
    setTimeout(() => toast.classList.add('oh-notification--show'), 10);

    // Auto remove
    setTimeout(() => {
      toast.classList.remove('oh-notification--show');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  /**
   * Show confirmation dialog
   */
  showConfirmDialog(title, message, onConfirm) {
    const confirmed = confirm(`${title}\n\n${message}`);
    if (confirmed && onConfirm) {
      onConfirm();
    }
  }

  /**
   * Debounce utility
   */
  debounce(fn, delay) {
    let timeoutId;
    return function (...args) {
      if (timeoutId) clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fn(...args), delay);
    };
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  // Check if page is settings page
  if (document.querySelector('.oh-settings-page')) {
    window.settingsManager = new SettingsPageManager();
  }
});

// ============================================================
// Notification Toast Styles (for runtime injection)
// ============================================================

const notificationStyles = `
  .oh-notification {
    position: fixed;
    bottom: 100px;
    right: 20px;
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    opacity: 0;
    transform: translateY(20px);
    transition: all 300ms ease;
    z-index: 250;
    max-width: 300px;
    word-wrap: break-word;
  }

  .oh-notification--show {
    opacity: 1;
    transform: translateY(0);
  }

  .oh-notification--success {
    background: #D1FAE5;
    color: #065F46;
    border-left: 4px solid #10B981;
  }

  .oh-notification--error {
    background: #FEE2E2;
    color: #7F1D1D;
    border-left: 4px solid #EF4444;
  }

  .oh-notification--info {
    background: #DBEAFE;
    color: #1E3A8A;
    border-left: 4px solid #3B82F6;
  }

  .oh-notification--warning {
    background: #FEF3C7;
    color: #78350F;
    border-left: 4px solid #F59E0B;
  }

  @media (max-width: 640px) {
    .oh-notification {
      bottom: 90px;
      right: 10px;
      left: 10px;
      max-width: none;
    }
  }
`;

// Inject notification styles
const styleElement = document.createElement('style');
styleElement.textContent = notificationStyles;
document.head.appendChild(styleElement);
