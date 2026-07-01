import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("admin@leadunify.com");
  const [password, setPassword] = useState("admin123");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    const fn = mode === "login" ? login(email, password) : register(email, password, name);
    const result = await fn;
    setLoading(false);
    if (result.ok) {
      toast.success(mode === "login" ? "Signed in" : "Account created");
      navigate("/people", { replace: true });
    } else {
      toast.error(result.error);
    }
  };

  return (
    <div className="min-h-screen w-full bg-slate-50 flex">
      {/* Left brand rail */}
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-white border-r border-slate-200 p-10 relative overflow-hidden">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-md bg-indigo-600 flex items-center justify-center text-white shadow-sm">
            <Sparkles className="w-4 h-4" strokeWidth={2.4} />
          </div>
          <div>
            <div className="text-[15px] font-bold tracking-tight text-slate-900">LeadUnify</div>
            <div className="text-[11px] text-slate-500">Contact intelligence</div>
          </div>
        </div>

        <div className="max-w-md">
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-slate-900 leading-[1.05]">
            One clean database.<br />
            <span className="text-indigo-600">Zero duplicate outreach.</span>
          </h1>
          <p className="mt-4 text-slate-600 leading-relaxed">
            Consolidate every prospect sheet you run — imports, events, nurture sequences — into a
            single source of truth where each person exists exactly once and every campaign they
            touch is visible at a glance.
          </p>

          <div className="mt-8 grid grid-cols-2 gap-3">
            <div className="p-4 bg-slate-50 rounded-md border border-slate-200">
              <div className="text-2xl font-bold text-slate-900 text-mono">100+</div>
              <div className="text-xs text-slate-500 mt-1">active campaigns supported</div>
            </div>
            <div className="p-4 bg-slate-50 rounded-md border border-slate-200">
              <div className="text-2xl font-bold text-slate-900 text-mono">50k+</div>
              <div className="text-xs text-slate-500 mt-1">contacts scale-ready</div>
            </div>
          </div>
        </div>

        <div className="text-[11px] text-slate-400">
          Internal tool — never publicly accessible.
        </div>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <Card className="w-full max-w-md border-slate-200 shadow-sm">
          <CardContent className="p-8">
            <div className="flex items-center gap-2 lg:hidden mb-6">
              <div className="w-8 h-8 rounded-md bg-indigo-600 flex items-center justify-center text-white">
                <Sparkles className="w-4 h-4" strokeWidth={2.4} />
              </div>
              <div className="text-[15px] font-bold tracking-tight">LeadUnify</div>
            </div>

            <h2 className="text-2xl font-bold tracking-tight text-slate-900">
              {mode === "login" ? "Sign in" : "Create your account"}
            </h2>
            <p className="text-sm text-slate-500 mt-1">
              {mode === "login"
                ? "Access your unified contact directory."
                : "You'll be added as a Member. Ask an admin to promote you."}
            </p>

            <form onSubmit={submit} className="mt-6 space-y-4">
              {mode === "register" && (
                <div>
                  <Label htmlFor="name">Name</Label>
                  <Input
                    id="name"
                    data-testid="register-name-input"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Alex Rivera"
                    className="mt-1.5"
                  />
                </div>
              )}
              <div>
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  data-testid="login-email-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1.5 text-mono"
                  required
                />
              </div>
              <div>
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  data-testid="login-password-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1.5 text-mono"
                  required
                />
              </div>

              <Button
                type="submit"
                data-testid={mode === "login" ? "login-submit-btn" : "register-submit-btn"}
                disabled={loading}
                className="w-full bg-indigo-600 hover:bg-indigo-700 text-white"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : mode === "login" ? "Sign in" : "Create account"}
              </Button>
            </form>

            <div className="mt-6 text-sm text-slate-500 text-center">
              {mode === "login" ? (
                <>
                  Need an account?{" "}
                  <button
                    type="button"
                    data-testid="switch-to-register"
                    onClick={() => setMode("register")}
                    className="text-indigo-600 hover:text-indigo-700 font-medium"
                  >
                    Create one
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    data-testid="switch-to-login"
                    onClick={() => setMode("login")}
                    className="text-indigo-600 hover:text-indigo-700 font-medium"
                  >
                    Sign in
                  </button>
                </>
              )}
            </div>

            {mode === "login" && (
              <div className="mt-4 p-3 bg-slate-50 rounded-md border border-slate-200 text-xs text-slate-600">
                <div className="font-medium text-slate-700 mb-1">Demo credentials pre-filled</div>
                <div className="text-mono text-slate-500">admin@leadunify.com / admin123</div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
