# Horilla Settings Redesign - Architecture & Design System

## 1. Information Architecture

### Current Issues:
- ❌ Cluttered accordion-based sidebar
- ❌ No visual grouping or hierarchy
- ❌ Inconsistent spacing and typography
- ❌ Poor mobile responsiveness
- ❌ No visual feedback for active states

### Proposed Solution: **Multi-Level Sidebar Navigation**

```
┌─────────────────────────────────────────────────────┐
│  SETTINGS HEADER                                    │
├──────────────┬──────────────────────────────────────┤
│ PRIMARY MENU │ SECONDARY MENU    │ CONTENT AREA    │
│              │                   │                 │
│ • General    │ • General Setting │ [Form Content] │
│ • Base       │ • Permissions     │                 │
│ • Recruitment│ • Accessibility   │                 │
│ • Employee   │ • User Groups     │                 │
│ • Attendance │                   │                 │
│ • Leave      │                   │                 │
│ • Payroll    │                   │                 │
│              │                   │                 │
└──────────────┴───────────────────┴─────────────────┘
```

### Why Vertical Sidebar Over Top Tabs?

| Aspect | Vertical Sidebar | Top Tabs |
|--------|------------------|----------|
| **Scalability** | ✅ Handles 10+ sections | ❌ Breaks with 5+ tabs |
| **Submenu Support** | ✅ Easy hierarchies | ❌ Limited grouping |
| **Mobile** | ✅ Collapsible drawer | ❌ Overflow issues |
| **Real Estate** | ✅ More content space | ❌ Eats horizontal space |
| **Professional Look** | ✅ Enterprise standard | ❌ Web app feel |

---

## 2. Visual Hierarchy & Design Principles

### Color Palette
```
Primary Actions:     #3B82F6 (Blue - Professional)
Danger Actions:      #EF4444 (Red - Warning)
Success:             #10B981 (Green - Confirmation)
Neutral/Borders:     #E5E7EB (Light Gray)
Text Primary:        #1F2937 (Dark Gray)
Text Secondary:      #6B7280 (Medium Gray)
Background:          #FFFFFF (Clean White)
Sidebar Background:  #F9FAFB (Subtle Gray)
Hover State:         #F3F4F6 (Light Gray)
Active State:        #EFF6FF (Light Blue)
```

### Typography
```
Page Title:          Inter 28px Bold (#1F2937)
Section Title:       Inter 18px SemiBold (#1F2937)
Labels:              Inter 14px SemiBold (#374151)
Input Text:          Inter 14px Regular (#1F2937)
Help Text:           Inter 12px Regular (#6B7280)
Sidebar Links:       Inter 13px Regular (#4B5563)
```

### Spacing System (8px base)
```
xs: 4px
sm: 8px
md: 12px
lg: 16px
xl: 24px
2xl: 32px
```

---

## 3. Component Hierarchy

### Settings Page Structure
```
1. Header Bar (Fixed)
   - Page Title
   - Breadcrumbs
   - Help/Info Button

2. Main Container
   ├─ Left Sidebar (280px fixed)
   │  ├─ Primary Navigation (Categories)
   │  ├─ Secondary Navigation (Subcategories)
   │  └─ Help/Support Link
   │
   ├─ Right Content Area
   │  ├─ Form Header
   │  │  ├─ Title & Description
   │  │  └─ Icon/Visual
   │  │
   │  ├─ Form Body
   │  │  ├─ Form Groups (Organized Sections)
   │  │  ├─ Dividers between sections
   │  │  └─ Consistent Spacing
   │  │
   │  └─ Form Footer
   │     ├─ Action Buttons
   │     └─ Danger Zone (if applicable)
   │
   └─ Sticky Save Bar (Bottom of viewport)
      └─ Changes detected? → Show Save/Discard buttons
```

---

## 4. Form Design System

### Form Group Container
```
┌─────────────────────────────────────────┐
│ ▪ Section Title (optional)              │
│ Description text if needed              │
├─────────────────────────────────────────┤
│ ┌─ Label [?] (Help icon)               │
│ ├─ Input Field (or Multiple columns)   │
│ ├─ Help Text / Validation Message      │
│ │                                       │
│ ├─ Label [?]                           │
│ ├─ Input Field                         │
│ └─ Help Text                           │
└─────────────────────────────────────────┘
```

### Input States
```
Default:         Background: #F3F4F6, Border: 1px #D1D5DB
Focus:           Background: #FFFFFF, Border: 2px #3B82F6, Shadow: 0 0 0 3px #DBEAFE
Error:           Background: #FEF2F2, Border: 1px #FCA5A5, Text: #DC2626
Success:         Background: #F0FDF4, Border: 1px #86EFAC, Icon: ✓
Disabled:        Background: #F9FAFB, Border: 1px #E5E7EB, Opacity: 0.6
```

---

## 5. Enterprise UX Patterns

### Change Detection System
```
1. Form Mount → Initialize baseline state
2. User Input → Compare with baseline
3. Changes Detected → Show sticky save bar
4. Save Click → Submit & clear baseline
5. Discard Click → Reset form & hide save bar
6. Navigation Away → Prompt if unsaved changes
```

### Danger Zone Pattern
```
┌─────────────────────────────────────────┐
│ ⚠️  DANGER ZONE                         │
│                                         │
│ Delete Company Data                     │
│ This action cannot be undone.          │
│ All associated data will be removed.   │
│                                         │
│ [Delete Company Data] (Outlined Red)   │
│                                         │
│ → On Click: Confirmation Modal         │
│    "Type 'DELETE' to confirm"          │
│    [Cancel] [Permanently Delete]       │
└─────────────────────────────────────────┘
```

---

## 6. Responsive Breakpoints

```
Mobile (< 640px):
- Sidebar becomes bottom drawer/hamburger menu
- Content full-width
- Sticky save bar remains visible

Tablet (640px - 1024px):
- Sidebar collapses to 200px
- Reduced font sizes
- Adjusted spacing

Desktop (> 1024px):
- Full sidebar (280px)
- Optimal spacing & typography
- Multi-column forms where appropriate
```

---

## 7. Animation & Interactions

### Transition Timing
```
Fast:       150ms (hover, focus states)
Normal:     300ms (sidebar toggle, modal open)
Slow:       500ms (page transitions)
```

### Key Interactions
1. **Sidebar Selection**: Smooth scroll to active item, highlight with left border
2. **Save Bar**: Slide up from bottom with 300ms ease-out
3. **Form Submit**: Loading spinner, success toast notification
4. **Validation**: Inline error messages with 150ms fade-in

---

## 8. Accessibility

- ✅ WCAG 2.1 AA compliant
- ✅ Keyboard navigation support (Tab, Arrow keys)
- ✅ ARIA labels on all inputs
- ✅ Focus indicators visible (2px blue outline)
- ✅ Color not sole differentiator (icons + text)
- ✅ Help text linked to inputs via aria-describedby

---

## 9. Performance Considerations

- Lazy-load secondary navigation on menu item hover
- Debounce change detection (200ms)
- CSS Grid for responsive layouts (no JS)
- Minimize repaints with CSS classes (no inline styles)
- Compress SVG icons inline
