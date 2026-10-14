import React from "react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import { Toaster } from "sonner";

export default function AppShell({ children }) {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <Topbar />
      <main className="ml-64 pt-14 min-h-screen">
        <div className="p-6 sm:p-8 space-y-6 max-w-[1600px] mx-auto">{children}</div>
      </main>
      <Toaster position="top-right" richColors />
    </div>
  );
}
