import { BrowserRouter, Routes, Route } from "react-router-dom";
import HomePage from "./Views/HomePage";
import SwingAIPage from "./Views/SwingAIPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/swingai" element={<SwingAIPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
