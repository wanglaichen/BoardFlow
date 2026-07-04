import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "mind-elixir/style.css";
import "@boardflow/editor-shell/styles.css";
import "./mindmap.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
