/* A shared, keyboard-accessible select surface for toolbar, detail and dialogs. */
(() => {
  const controls = new Map();
  let sequence = 0, opened = null, frame = 0, typed = '', typedAt = 0;
  const editable = node => node instanceof Element && node.closest('input,textarea,[contenteditable="true"]');
  document.addEventListener('dragstart', event => { if (!editable(event.target)) event.preventDefault(); });

  function closeMenu(focus = false) {
    if (!opened) return;
    const {menu, button} = opened;
    opened = null;
    if (menu.matches(':popover-open')) menu.hidePopover();
    menu.remove();
    button.setAttribute('aria-expanded', 'false');
    button.removeAttribute('aria-activedescendant');
    if (focus && button.isConnected) button.focus({preventScroll:true});
  }
  function sync(control) {
    const {select, wrap, button, label} = control;
    const caption = select.selectedOptions[0]?.textContent || '请选择';
    if (label.textContent !== caption) label.textContent = caption;
    if (wrap.hidden !== select.hidden) wrap.hidden = select.hidden;
    if (button.disabled !== select.disabled) button.disabled = select.disabled;
    const name = select.getAttribute('aria-label') || [...(select.labels || [])].map(l => l.textContent).join(' ') || '选择选项';
    button.setAttribute('aria-label', name);
    button.title = caption;
    if (opened?.control === control && (select.hidden || select.disabled)) closeMenu();
  }
  function setActive(index) {
    if (!opened) return;
    const entry = opened.entries[index];
    if (!entry || entry.disabled) return;
    opened.active = index;
    opened.entries.forEach((row, n) => row.node.classList.toggle('is-active', n === index));
    opened.button.setAttribute('aria-activedescendant', entry.node.id);
    entry.node.scrollIntoView({block:'nearest'});
  }
  function choose(index) {
    const state = opened, entry = state?.entries[index];
    if (!entry || entry.disabled) return;
    const select = state.control.select, changed = select.selectedIndex !== entry.index;
    select.selectedIndex = entry.index;
    closeMenu(true);
    sync(state.control);
    if (changed) {
      select.dispatchEvent(new Event('input', {bubbles:true}));
      select.dispatchEvent(new Event('change', {bubbles:true}));
    }
  }
  function openMenu(control) {
    if (control.select.disabled || control.select.hidden) return;
    closeMenu(); sync(control); typed = '';
    const {select, button} = control;
    const menu = document.createElement('div');
    menu.className = 'studio-select-menu';
    menu.id = button.getAttribute('aria-controls');
    menu.setAttribute('popover', 'manual');
    menu.setAttribute('role', 'listbox');
    menu.setAttribute('aria-label', button.getAttribute('aria-label'));
    const entries = [];
    let group = null;
    [...select.options].forEach((option, index) => {
      if (option.hidden) return;
      const parent = option.parentElement;
      if (parent.tagName === 'OPTGROUP' && group !== parent) {
        group = parent;
        const heading = document.createElement('div');
        heading.className = 'studio-select-group'; heading.textContent = parent.label;
        heading.setAttribute('role', 'presentation'); menu.append(heading);
      }
      const node = document.createElement('div'), text = document.createElement('span');
      const disabled = option.disabled || (parent.tagName === 'OPTGROUP' && parent.disabled);
      node.className = 'studio-select-option'; node.id = menu.id + '-' + index;
      node.setAttribute('role', 'option');
      node.setAttribute('aria-selected', String(option.selected));
      node.setAttribute('aria-disabled', String(disabled));
      text.textContent = option.textContent;
      node.append(text);
      node.insertAdjacentHTML('beforeend', '<svg class="studio-select-check" viewBox="0 0 16 16" aria-hidden="true"><path d="m3 8 3 3 7-7"/></svg>');
      const n = entries.length;
      node.onpointermove = () => { if (opened?.active !== n) setActive(n); };
      node.onpointerdown = event => event.preventDefault();
      node.onclick = () => choose(n);
      entries.push({node, index, disabled, label:option.textContent}); menu.append(node);
    });
    // Inside an open dialog, the popover must also be inside its non-inert subtree.
    (button.closest('dialog') || document.body).append(menu);
    opened = {control, button, menu, entries, active:-1};
    button.setAttribute('aria-expanded', 'true');
    menu.showPopover();
    const rect = button.getBoundingClientRect(), below = innerHeight - rect.bottom - 18, above = rect.top - 18;
    const upward = below < Math.min(menu.scrollHeight, 240) && above > below;
    const height = Math.max(60, Math.min(360, upward ? above : below));
    menu.style.width = Math.min(innerWidth - 24, Math.max(rect.width, 196)) + 'px';
    menu.style.maxHeight = height + 'px';
    menu.style.left = Math.max(12, Math.min(rect.left, innerWidth - menu.getBoundingClientRect().width - 12)) + 'px';
    menu.style.top = (upward ? Math.max(12, rect.top - menu.getBoundingClientRect().height - 7) : rect.bottom + 7) + 'px';
    setActive(entries.findIndex(e => e.index === select.selectedIndex && !e.disabled));
  }
  function enhance(select) {
    if (controls.has(select) || select.multiple || select.size > 1) return;
    const wrap = document.createElement('span');
    wrap.className = 'studio-select ' + select.className;
    wrap.dataset.selectId = select.id;
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'studio-select-trigger';
    button.setAttribute('role', 'combobox'); button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-controls', 'studio-options-' + (++sequence));
    const label = document.createElement('span'); label.className = 'studio-select-label';
    button.append(label);
    button.insertAdjacentHTML('beforeend', '<svg class="studio-select-chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg>');
    select.before(wrap); wrap.append(select, button);
    select.tabIndex = -1; select.setAttribute('aria-hidden', 'true');
    const control = {select, wrap, button, label}; controls.set(select, control);
    button.onclick = () => opened?.control === control ? closeMenu() : openMenu(control);
    select.addEventListener('change', () => sync(control));
    select.addEventListener('focus', () => button.focus());
    button.addEventListener('keydown', event => {
      const key = event.key;
      if (key === 'Tab') { closeMenu(); return; }
      if (key === 'Escape' && opened?.control === control) {
        event.preventDefault(); event.stopImmediatePropagation(); closeMenu(); return;
      }
      if (['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(key)) {
        event.preventDefault(); event.stopPropagation();
        if (opened?.control !== control) { openMenu(control); return; }
        if (key === 'Enter' || key === ' ') { choose(opened.active); return; }
        const eligible = opened.entries.map((e,n) => e.disabled ? -1 : n).filter(n => n >= 0);
        const at = eligible.indexOf(opened.active);
        const next = key === 'Home' ? 0 : key === 'End' ? eligible.length-1 : Math.max(0, Math.min(eligible.length-1, at + (key === 'ArrowDown' ? 1 : -1)));
        setActive(eligible[next]);
      } else if (key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        if (opened?.control !== control) openMenu(control);
        const now = Date.now(); typed = now - typedAt < 700 ? typed + key : key; typedAt = now;
        setActive(opened.entries.findIndex(e => !e.disabled && e.label.toLocaleLowerCase().startsWith(typed.toLocaleLowerCase())));
      }
    });
    sync(control);
  }
  function refresh() {
    frame = 0;
    for (const [select, control] of controls) {
      if (!select.isConnected) { if (opened?.control === control) closeMenu(); controls.delete(select); }
      else sync(control);
    }
    document.querySelectorAll('select').forEach(enhance);
  }
  new MutationObserver(() => { if (!frame) frame = requestAnimationFrame(refresh); })
    .observe(document.body, {subtree:true, childList:true, attributes:true, attributeFilter:['hidden','disabled','selected','label']});
  document.addEventListener('pointerdown', event => {
    if (opened && !opened.menu.contains(event.target) && !opened.button.contains(event.target)) closeMenu();
  }, true);
  document.addEventListener('scroll', event => { if (opened && !opened.menu.contains(event.target)) closeMenu(); }, true);
  document.addEventListener('close', () => closeMenu(), true);
  document.addEventListener('focusin', event => { if (opened && event.target !== opened.button && !opened.menu.contains(event.target)) closeMenu(); });
  window.addEventListener('resize', () => closeMenu());
  window.addEventListener('blur', () => closeMenu());
  refresh();
})();
