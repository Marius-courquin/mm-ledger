import React from "react";
import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";
import { theme } from "./theme";

const App: React.FC = () => {
  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        width: "100vw",
        background: theme.colors.background,
        fontFamily: theme.font.family,
        color: theme.colors.textPrimary,
        overflow: "hidden",
      }}
    >
      <Sidebar />
      <main
        style={{
          flex: 1,
          overflowY: "auto",
          padding: theme.spacing["2xl"],
        }}
      >
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/portfolio" element={<Dashboard />} />
          <Route path="/accounts" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
};

export default App;
