import { createRoot } from 'react-dom/client';
import { createApplication } from './app/composition';
import { App } from './app/App';
import './app/styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('Missing application root');
createRoot(root).render(<App application={createApplication()} />);
