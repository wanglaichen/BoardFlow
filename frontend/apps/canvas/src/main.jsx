import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "tldraw/tldraw.css";
import "@boardflow/editor-shell/styles.css";
import "./canvas.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
