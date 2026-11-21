import { createRoot } from 'react-dom/client';

import { App } from './App';
import { applyStoredTheme } from './theme/theme';
import './theme/tokens.css';
import './app.css';

applyStoredTheme();

const host = document.getElementById('root');
if (!host) throw new Error('#root is missing from index.html');
createRoot(host).render(<App />);
