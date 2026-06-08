import './App.css'

function App() {
  return (
    <main className="app-shell">
      <header>
        <h1>ETEN Admin</h1>
        <p className="tagline">React + Vite frontend (migration in progress)</p>
      </header>
      <section className="panel">
        <p>
          The Flask admin UI still runs at{' '}
          <a href="http://localhost:7860/admin" target="_blank" rel="noreferrer">
            /admin
          </a>{' '}
          while screens move here as JSON APIs are added under <code>/api/v1</code>.
        </p>
      </section>
    </main>
  )
}

export default App
