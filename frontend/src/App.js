import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import AppLayout from "@/components/AppLayout";
import LoginPage from "@/pages/Login";
import PeoplePage from "@/pages/People";
import CompaniesPage from "@/pages/Companies";
import CampaignsPage from "@/pages/Campaigns";
import ImportPage from "@/pages/Import";
import DuplicatesPage from "@/pages/Duplicates";
import DashboardPage from "@/pages/Dashboard";
import { Toaster } from "@/components/ui/sonner";

function LoginRedirectIfAuthed({ children }) {
  const { user, checked } = useAuth();
  if (!checked) return null;
  if (user) return <Navigate to="/people" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="/login"
            element={
              <LoginRedirectIfAuthed>
                <LoginPage />
              </LoginRedirectIfAuthed>
            }
          />
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/people" replace />} />
            <Route path="/people" element={<PeoplePage />} />
            <Route path="/companies" element={<CompaniesPage />} />
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/duplicates" element={<DuplicatesPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="*" element={<Navigate to="/people" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors closeButton />
    </AuthProvider>
  );
}
