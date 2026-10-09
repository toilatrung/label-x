/* Local fallback for the existing .dc.html design format.
 * The published canvas supplies its own DCLogic; this fallback only runs without it.
 * Serve docs/design over HTTP to resolve shared dc-import components.
 */
(() => {
  if (window.DCLogic) return;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const read = (scope, expression) => {
    expression = expression.trim().replace(/^{{|}}$/g, '').trim();
    if (expression === 'true') return true;
    if (expression === 'false') return false;
    return expression.split('.').reduce((value, key) => value?.[key], scope);
  };
  const definitions = new Map();
  function definition(source) {
    const script = source.match(/<script\b[^>]*type="text\/x-dc"[^>]*>([\s\S]*?)<\/script>/i);
    const props = source.match(/data-props='([^']*)'/);
    if (!script) throw new Error('Missing canvas component logic.');
    return {template:source.match(/<x-dc[^>]*>([\s\S]*?)<\/x-dc>/i)?.[1] || '',
      props:props ? JSON.parse(props[1]) : {},
      Class:Function('DCLogic', `${script[1]}\nreturn Component;`)(LocalLogic)};
  }
  async function load(name) {
    if (!/^[A-Za-z]+$/.test(name)) throw new Error('Invalid component name.');
    if (window.LabelXDesignSources?.[name]) return definition(window.LabelXDesignSources[name]);
    if (!definitions.has(name)) definitions.set(name, fetch(`${name}.dc.html`).then(async response => {
      if (!response.ok) throw new Error(`Cannot load ${name}.`);
      return definition(await response.text());
    }));
    return definitions.get(name);
  }
  function expand(source, scope, handlers) {
    // Expand directives as strings before DOM parsing so table rows stay in place.
    let result = ''; let cursor = 0;
    const opener = /<sc-(for|if)\b([^>]*)>/g;
    let match;
    while ((match = opener.exec(source))) {
      result += interpolate(source.slice(cursor, match.index), scope, handlers);
      const kind = match[1]; const bodyStart = opener.lastIndex;
      const tags = new RegExp(`<\\/?sc-${kind}\\b[^>]*>`, 'g'); tags.lastIndex = bodyStart;
      let depth = 1; let close;
      while ((close = tags.exec(source))) {
        depth += close[0].startsWith('</') ? -1 : 1;
        if (depth === 0) break;
      }
      if (!close || depth) throw new Error('Unclosed canvas directive.');
      const attrs = Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1],m[2]]));
      const body = source.slice(bodyStart, close.index);
      if (kind === 'if') {
        if (read(scope, attrs.value)) result += expand(body, scope, handlers);
      } else {
        const items = read(scope, attrs.list) || [];
        for (const item of items) result += expand(body, {...scope, [attrs.as]:item}, handlers);
      }
      cursor = tags.lastIndex; opener.lastIndex = cursor;
    }
    return result + interpolate(source.slice(cursor), scope, handlers);
  }
  function interpolate(source, scope, handlers) {
    source = source.replace(/\bon(click|input|change)="{{([^}]+)}}"/gi, (_, event, key) => {
      const callback = read(scope, key); const id = handlers.length;
      handlers.push({event:event.toLowerCase(),callback});
      return `data-lx-handler-${event.toLowerCase()}="${id}"`;
    });
    source = source.replace(/\b(checked|disabled|selected)="{{([^}]+)}}"/g, (_, attr, key) => read(scope,key) ? attr : '');
    return source.replace(/{{([^}]+)}}/g, (_, key) => escape(read(scope,key)));
  }
  class LocalLogic {
    constructor() { this.state = {}; this.props = {}; this.children = new Map(); this.generation = 0; }
    setState(next) { Object.assign(this.state,next); return this.draw().catch(showError); }
    async draw() {
      const version = ++this.generation;
      const focus = document.activeElement;
      const focusId = this.host.contains(focus) ? focus.id : '';
      const selection = focusId && typeof focus.selectionStart === 'number' ? [focus.selectionStart,focus.selectionEnd] : null;
      const handlers = [];
      const html = expand(this.template, this.renderVals(), handlers);
      if (version !== this.generation) return;
      this.host.innerHTML = html;
      for (const [id,handler] of handlers.entries()) {
        const attr = `data-lx-handler-${handler.event}`;
        const node = this.host.querySelector(`[${attr}="${id}"]`);
        if (node) {
          node.removeAttribute(attr);
          if (node.matches('[aria-haspopup="menu"]')) node.id ||= 'lx-menu-' + node.textContent.trim().replace(/[^a-zA-Z0-9]+/g,'-');
          node.addEventListener(handler.event, event => handler.callback?.(event));
        }
      }
      // value attributes on select/textarea must be applied to their DOM properties.
      this.host.querySelectorAll('select[value],textarea[value]').forEach(node => {node.value=node.getAttribute('value');});
      const imports = [...this.host.querySelectorAll('dc-import')];
      await Promise.all(imports.map(async (node,index) => {
        const def = await load(node.getAttribute('name'));
        if (version !== this.generation) return;
        let child = this.children.get(index);
        if (!child) { child = new def.Class(); this.children.set(index,child); }
        child.props = defaults(def.props);
        for (const attr of node.attributes) {
          const key = attr.name.replace(/-([a-z])/g,(_,c)=>c.toUpperCase());
          child.props[key] = attr.value === 'true' ? true : attr.value === 'false' ? false : attr.value;
        }
        child.host = node; child.template = def.template;
        await child.draw();
      }));
      if (focusId) {
        const restored = document.getElementById(focusId);
        restored?.focus({preventScroll:true});
        if (selection) restored?.setSelectionRange(...selection);
      }
      this.host.querySelectorAll('.lx-menu').forEach(menu => {
        menu.addEventListener('keydown',event => {
          const items=[...menu.querySelectorAll('[role="menuitem"]')]; const idx=items.indexOf(document.activeElement);
          if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
            event.preventDefault(); const next=event.key==='Home'?0:event.key==='End'?items.length-1:(idx+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;
            items[next]?.focus();
          }
        });
      });
      this.host.querySelectorAll('[aria-haspopup="menu"]').forEach(button => {
        button.addEventListener('keydown',event => {
          if (event.key==='ArrowDown') { event.preventDefault();button.click();setTimeout(()=>this.host.querySelector('.lx-menu [role="menuitem"]')?.focus(),0); }
        });
      });
    }
  }
  const defaults = props => Object.fromEntries(Object.entries(props).filter(([key])=>key!=='$preview').map(([key,value])=>[key,value.default]));
  function showError(error) {
    console.error(error);
    const note=document.createElement('p');note.setAttribute('role','alert');note.textContent='Không tải được bản thiết kế. Hãy mở qua HTTP (python3 -m http.server 4173 từ docs/design).';
    document.body.append(note);
  }
  document.addEventListener('DOMContentLoaded',async () => {
    try {
      let component;
      async function openScreen() {
        const name=location.hash.slice(1) || 'ReviewQueues';
        const source=window.LabelXDesignSources ? window.LabelXDesignSources[name] : await fetch(location.href).then(r=>r.text());
        if (!source) throw new Error('Unknown design screen.');
        const def=definition(source);component=new def.Class();
        component.props=defaults(def.props);component.template=def.template;component.host=document.querySelector('x-dc');
        await component.draw();
        document.title = source.match(/<title>(.*?)<\/title>/)?.[1] || 'LabelX Design';
      }
      await openScreen();
      if (window.LabelXDesignSources) {
        window.addEventListener('popstate',()=>openScreen().catch(showError));
        document.addEventListener('click',event=>{
          const link=event.target.closest('a[href]');const target=link?.getAttribute('href').match(/^([A-Za-z]+)\.dc\.html(\?[^#]*)?$/);
          if(!target)return;
          event.preventDefault();history.pushState(null,'',`${location.pathname}${target[2] || ''}#${target[1]}`);
          openScreen().then(()=>window.scrollTo(0,0)).catch(showError);
        });
      }
      document.addEventListener('keydown',async event=>{
        if(event.key!=='Escape')return;
        const triggerId=document.querySelector('[aria-haspopup="menu"][aria-expanded="true"]')?.id;
        const pending=[];
        const visit=instance=>{if(instance.state.open||instance.state.cx||instance.state.ux||instance.props.menuOpen){pending.push(instance.setState({open:null,cx:null,ux:false}));}instance.children.forEach(visit);};
        visit(component);await Promise.all(pending);
        if(triggerId)document.getElementById(triggerId)?.focus({preventScroll:true});
      });
    } catch(error) {showError(error);}
  });
})();
