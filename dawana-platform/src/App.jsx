import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/layout/SiteChrome'
import Home from './pages/Home'
import Programs from './pages/Programs'
import Events from './pages/Events'
import Projects from './pages/Projects'
import DIC from './pages/DIC'
import Media from './pages/Media'
import GetInvolved from './pages/GetInvolved'
import Contact from './pages/Contact'
import FAQ from './pages/FAQ'
import Donate from './pages/Donate'
import './App.css'

function App() {
  return <BrowserRouter><Layout><Routes><Route path="/" element={<Home />} /><Route path="/programs" element={<Programs />} /><Route path="/events" element={<Events />} /><Route path="/projects" element={<Projects />} /><Route path="/dic/*" element={<DIC />} /><Route path="/media" element={<Media />} /><Route path="/get-involved" element={<GetInvolved />} /><Route path="/contact" element={<Contact />} /><Route path="/faq" element={<FAQ />} /><Route path="/donate" element={<Donate />} /><Route path="*" element={<PlaceholderPage />} /></Routes></Layout></BrowserRouter>
}

function PlaceholderPage() {
  return <section className="placeholder-page"><span className="eyebrow">Da&apos;wãnã Islamic Foundation</span><h1>This page is being prepared.</h1><p>More details will be added as official content becomes available.</p></section>
}

export default App
