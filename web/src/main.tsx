import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// Log για αποσφαλμάτωση
console.log('NYC Subway Monitor starting...');
console.log('Tailwind CSS should be loaded');

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);