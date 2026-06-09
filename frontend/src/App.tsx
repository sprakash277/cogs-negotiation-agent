import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Hub from "./pages/Hub";
import Negotiator from "./pages/Negotiator";
import Scorecard from "./pages/Scorecard";
import Brief from "./pages/Brief";
import Rehearsal from "./pages/Rehearsal";
import Deck from "./pages/Deck";

export default function App() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Hub />} />
          <Route path="/negotiator" element={<Negotiator />} />
          <Route path="/scorecard" element={<Scorecard />} />
          <Route path="/scorecard/:supplier" element={<Scorecard />} />
          <Route path="/brief/:supplier" element={<Brief />} />
          <Route path="/deck/:supplier" element={<Deck />} />
          <Route path="/rehearse/:supplier" element={<Rehearsal />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
