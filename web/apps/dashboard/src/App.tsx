import { BrowserRouter, Routes, Route } from 'react-router'

function HomePage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-950 text-neutral-50">
      <div className="text-center">
        <h1 className="text-4xl font-bold tracking-tight">Lunar Sandbox</h1>
        <p className="mt-2 text-lg text-neutral-400">Dashboard</p>
      </div>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
