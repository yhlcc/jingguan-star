import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../layouts/AppShell";

const DashboardPage = lazy(() => import("../features/dashboard/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const AssistantPage = lazy(() => import("../features/assistant/AssistantPage").then((module) => ({ default: module.AssistantPage })));
const InterfacesPage = lazy(() => import("../features/interfaces/InterfacesPage").then((module) => ({ default: module.InterfacesPage })));
const AuditsPage = lazy(() => import("../features/audits/AuditsPage").then((module) => ({ default: module.AuditsPage })));
const FeedbackPage = lazy(() => import("../features/feedback/FeedbackPage").then((module) => ({ default: module.FeedbackPage })));
const SettingsPage = lazy(() => import("../features/settings/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const SkillsPage = lazy(() => import("../features/skills/SkillsPage").then((module) => ({ default: module.SkillsPage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<div className="empty">正在加载业务模块…</div>}>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/assistant" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/assistant" element={<AssistantPage />} />
              <Route path="/audits" element={<AuditsPage />} />
              <Route path="/feedback" element={<FeedbackPage />} />
              <Route path="/interfaces" element={<InterfacesPage />} />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
