import re

def html_to_jsx(html):
    # Replace class= with className=
    html = re.sub(r'\bclass=', 'className=', html)
    # Replace for= with htmlFor=
    html = re.sub(r'\bfor=', 'htmlFor=', html)
    
    # Self-close common tags
    for tag in ['img', 'hr', 'br', 'input', 'meta', 'link']:
        html = re.sub(rf'<{tag}([^>]*?)(?<!/)>', rf'<{tag}\1 />', html, flags=re.IGNORECASE)
    
    # Fix inline styles (basic regex replace, might need manual tweaks for complex styles)
    def style_replacer(match):
        style_str = match.group(1)
        styles = []
        for prop in style_str.split(';'):
            if not prop.strip(): continue
            parts = prop.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                # camelCase key
                parts_key = key.split('-')
                key = parts_key[0] + ''.join(word.capitalize() for word in parts_key[1:])
                val = parts[1].strip()
                styles.append(f"'{key}': '{val}'")
        return 'style={{' + ', '.join(styles) + '}}'
        
    html = re.sub(r'style="([^"]*)"', style_replacer, html)
    
    return html

with open('public/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract body
body_match = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL | re.IGNORECASE)
if body_match:
    body_content = body_match.group(1)
    # Remove script tags from body for React component, we will handle them in useEffect
    body_content = re.sub(r'<script.*?</script>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
    
    jsx_content = html_to_jsx(body_content)
    
    with open('src/pages/Masterclass.tsx', 'w', encoding='utf-8') as out:
        out.write(f'''
import React, {{ useEffect }} from 'react';
import {{ useAuth }} from '../lib/AuthContext';
import {{ useNavigate }} from 'react-router-dom';

export default function Masterclass() {{
  const {{ user, signOut }} = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {{
    await signOut();
    navigate('/login');
  }};

  useEffect(() => {{
    // Pyodide initialization script
    const script = document.createElement('script');
    script.src = "https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js";
    document.body.appendChild(script);
    
    // Original JS logic here
    // Note: for full functionality the original scripts need to be adapted or mounted
  }}, []);

  return (
    <div>
      <div className="bg-dark text-white p-2 text-end">
         <span className="me-3">Estudiante: {{user?.email}}</span>
         <button onClick={{handleLogout}} className="btn btn-sm btn-danger">Cerrar Sesión</button>
      </div>
      {{/* Contenido original convertido a JSX */}}
      {jsx_content}
    </div>
  );
}}
''')
    print("Masterclass.tsx created successfully!")
else:
    print("Could not find body tag")

