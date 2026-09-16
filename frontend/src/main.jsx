import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './index.css';
class ErrorBoundary extends React.Component {
  state = {failed: false};
  static getDerivedStateFromError() {return {failed: true};}
  render() {return this.state.failed ? <main className="flex min-h-screen flex-col items-center justify-center p-8"><h1 className="text-2xl font-semibold">Your cinema needs a refresh.</h1><p className="my-4 text-muted">An unexpected interface error interrupted this session.</p><button className="btn-primary" onClick={() => window.location.reload()}>Reload Jishflix</button></main> : this.props.children;}
}
ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><ErrorBoundary><BrowserRouter><App/></BrowserRouter></ErrorBoundary></React.StrictMode>);
