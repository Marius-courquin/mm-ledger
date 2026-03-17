import React, { useState, useEffect, useRef } from "react";
import { Plug, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { theme } from "../theme";

// ── Styles ─────────────────────────────────────────────────────────────────────

const card: React.CSSProperties = {
  background: theme.colors.surface,
  border: `1px solid ${theme.colors.border}`,
  borderRadius: theme.radius.lg,
  padding: theme.spacing.lg,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: `${theme.spacing.sm + 2}px ${theme.spacing.md}px`,
  background: theme.colors.surfaceElevated,
  border: `1px solid ${theme.colors.border}`,
  borderRadius: theme.radius.md,
  color: theme.colors.textPrimary,
  fontSize: 14,
  outline: "none",
  transition: "border-color 0.15s ease",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 13,
  fontWeight: 500,
  color: theme.colors.textSecondary,
  marginBottom: theme.spacing.xs,
};

const buttonPrimary: React.CSSProperties = {
  padding: `${theme.spacing.sm + 2}px ${theme.spacing.lg}px`,
  background: theme.colors.accentGold,
  color: theme.colors.surface,
  border: "none",
  borderRadius: theme.radius.md,
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
  transition: "opacity 0.15s ease",
};

const buttonSecondary: React.CSSProperties = {
  padding: `${theme.spacing.sm + 2}px ${theme.spacing.lg}px`,
  background: "transparent",
  color: theme.colors.textSecondary,
  border: `1px solid ${theme.colors.border}`,
  borderRadius: theme.radius.md,
  fontSize: 14,
  fontWeight: 500,
  cursor: "pointer",
  transition: "all 0.15s ease",
};

// ── Component ──────────────────────────────────────────────────────────────────

const Settings: React.FC = () => {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [pin, setPin] = useState("");
  const [devicePin, setDevicePin] = useState("");
  const [connected, setConnected] = useState(false);
  const [waitingForPin, setWaitingForPin] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // BP state
  const [bpLogin, setBpLogin] = useState("");
  const [bpPassword, setBpPassword] = useState("");
  const [bpRegion, setBpRegion] = useState("10207");
  const [bpConnected, setBpConnected] = useState(false);
  const [bpWaiting2FA, setBpWaiting2FA] = useState<false | "sms" | "app">(false);
  const [bp2FAMessage, setBp2FAMessage] = useState("");
  const [bpLoading, setBpLoading] = useState(false);
  const [bpMessage, setBpMessage] = useState("");

  const BP_REGIONS: Record<string, string> = {
    "14707": "Alsace Lorraine Champagne",
    "10907": "Aquitaine Centre Atlantique",
    "16807": "Auvergne Rhone Alpes",
    "10807": "Bourgogne Franche Comté",
    "13807": "Grand Ouest",
    "14607": "Mediterranée",
    "13507": "Nord",
    "17807": "Occitane",
    "10207": "Rives de Paris",
    "16607": "Sud",
    "18707": "Val de France",
  };

  // Load current settings & poll for status changes
  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      const tr = data.connectors?.find((c: any) => c.id === "trade-republic");
      if (tr) {
        setConnected(tr.connected);
        setWaitingForPin(tr.waitingForPin);
        if (!phoneNumber && tr.phoneNumber) setPhoneNumber(tr.phoneNumber);
      }
      const bp = data.connectors?.find((c: any) => c.id === "banque-populaire");
      if (bp) {
        setBpConnected(bp.connected);
        setBpWaiting2FA(bp.waiting2FA || false);
        setBp2FAMessage(bp.message2FA || "");
        if (!bpLogin && bp.login) setBpLogin(bp.login);
        if (bp.region) setBpRegion(bp.region);
        if (bp.connected) setBpLoading(false);
      }
    } catch {}
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  // Poll while waiting for connection
  useEffect(() => {
    if (loading || waitingForPin || bpLoading || bpWaiting2FA) {
      pollRef.current = setInterval(fetchStatus, 2000);
      return () => {
        if (pollRef.current) clearInterval(pollRef.current);
      };
    }
  }, [loading, waitingForPin, bpLoading, bpWaiting2FA]);

  const handleSave = async () => {
    setLoading(true);
    setMessage("Saving credentials & connecting...");
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phoneNumber, pin }),
      });
      // Poll will pick up the status
      setMessage("Credentials saved. Check your TR app for 2FA if needed...");
    } catch {
      setMessage("Error saving settings");
      setLoading(false);
    }
  };

  const handleSubmitDevicePin = async () => {
    if (!devicePin) return;
    setMessage("Submitting 2FA code...");
    try {
      const res = await fetch("/api/auth/pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: devicePin }),
      });
      const data = await res.json();
      setConnected(data.connected);
      setWaitingForPin(false);
      setLoading(false);
      setDevicePin("");
      setMessage(data.connected ? "Connected!" : "Connection failed");
    } catch {
      setMessage("Error submitting PIN");
    }
  };

  const handleBpSave = async () => {
    setBpLoading(true);
    setBpMessage("Connexion en cours...");
    try {
      const res = await fetch("/api/bp/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: bpLogin, password: bpPassword, region: bpRegion }),
      });
      const data = await res.json();
      if (data.waiting2FA) {
        setBpWaiting2FA(data.waiting2FA);
        setBp2FAMessage(data.message || "");
        setBpMessage("Validation requise...");
      } else {
        setBpMessage("Identifiants sauvegardés...");
      }
    } catch {
      setBpMessage("Erreur de connexion");
      setBpLoading(false);
    }
  };

  const handleBpReset = async () => {
    try {
      await fetch("/api/bp/reset", { method: "POST" });
    } catch {}
    setBpConnected(false);
    setBpWaiting2FA(false);
    setBp2FAMessage("");
    setBpLoading(false);
    setBpMessage("");
  };

  const handleBpValidate2FA = async () => {
    setBpMessage("Validation en cours...");
    try {
      const res = await fetch("/api/bp/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method: "app" }),
      });
      const data = await res.json();
      setBpConnected(data.connected);
      setBpWaiting2FA(data.waiting2FA || false);
      setBpLoading(false);
      setBpMessage(data.connected ? "Connecté !" : "Échec de connexion");
    } catch {
      setBpMessage("Erreur de validation");
    }
  };

  // Stop loading when connected
  useEffect(() => {
    if (connected) {
      setLoading(false);
      if (pollRef.current) clearInterval(pollRef.current);
    }
  }, [connected]);

  return (
    <div style={{ maxWidth: 800 }}>
      {/* Header */}
      <div style={{ marginBottom: theme.spacing.xl }}>
        <h1
          style={{
            fontSize: 28,
            fontWeight: 700,
            color: theme.colors.textPrimary,
            marginBottom: theme.spacing.xs,
          }}
        >
          Settings
        </h1>
        <p style={{ fontSize: 14, color: theme.colors.textMuted }}>Connectors</p>
      </div>

      {/* Trade Republic connector card */}
      <div style={card}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: theme.spacing.lg,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: theme.spacing.sm }}>
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: theme.radius.md,
                background: `linear-gradient(135deg, ${theme.colors.accentLilac}, ${theme.colors.accentLavender})`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Plug size={22} color="#fff" />
            </div>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 600, color: theme.colors.textPrimary }}>
                Trade Republic
              </h3>
              <p style={{ fontSize: 12, color: theme.colors.textMuted }}>Brokerage connector</p>
            </div>
          </div>

          {/* Status indicator */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: theme.spacing.xs,
              padding: `${theme.spacing.xs}px ${theme.spacing.sm}px`,
              borderRadius: theme.radius.sm,
              background: waitingForPin
                ? `${theme.colors.accentLavender}15`
                : connected
                  ? `${theme.colors.accentGold}15`
                  : `${theme.colors.loss}15`,
              border: `1px solid ${
                waitingForPin
                  ? `${theme.colors.accentLavender}30`
                  : connected
                    ? `${theme.colors.accentGold}30`
                    : `${theme.colors.loss}30`
              }`,
            }}
          >
            {waitingForPin ? (
              <Loader2 size={14} color={theme.colors.accentLavender} style={{ animation: "spin 1s linear infinite" }} />
            ) : connected ? (
              <CheckCircle size={14} color={theme.colors.accentGold} />
            ) : (
              <XCircle size={14} color={theme.colors.loss} />
            )}
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: waitingForPin
                  ? theme.colors.accentLavender
                  : connected
                    ? theme.colors.accentGold
                    : theme.colors.loss,
              }}
            >
              {waitingForPin ? "Waiting for 2FA" : connected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>

        {/* Form */}
        <div style={{ display: "flex", flexDirection: "column", gap: theme.spacing.md }}>
          {/* 2FA PIN input — shown when backend is waiting */}
          {waitingForPin && (
            <div
              style={{
                padding: theme.spacing.md,
                background: `${theme.colors.accentLavender}10`,
                border: `1px solid ${theme.colors.accentLavender}30`,
                borderRadius: theme.radius.md,
              }}
            >
              <label style={{ ...labelStyle, color: theme.colors.accentLavender }}>
                2FA Code (check your Trade Republic app)
              </label>
              <div style={{ display: "flex", gap: theme.spacing.sm }}>
                <input
                  type="text"
                  placeholder="Enter 4-digit code"
                  value={devicePin}
                  onChange={(e) => setDevicePin(e.target.value)}
                  style={{ ...inputStyle, borderColor: `${theme.colors.accentLavender}50` }}
                  autoFocus
                />
                <button style={buttonPrimary} onClick={handleSubmitDevicePin}>
                  Verify
                </button>
              </div>
            </div>
          )}

          {!waitingForPin && (
            <>
              <div>
                <label style={labelStyle}>Phone Number</label>
                <input
                  type="text"
                  placeholder="+33 6 12 34 56 78"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  style={inputStyle}
                />
              </div>

              <div>
                <label style={labelStyle}>PIN</label>
                <input
                  type="password"
                  placeholder="Enter your PIN"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  style={inputStyle}
                />
              </div>
            </>
          )}

          {/* Message */}
          {message && (
            <div
              style={{
                fontSize: 13,
                color: connected
                  ? theme.colors.accentGold
                  : waitingForPin
                    ? theme.colors.accentLavender
                    : theme.colors.loss,
              }}
            >
              {message}
            </div>
          )}

          {/* Actions */}
          {!waitingForPin && (
            <div style={{ display: "flex", gap: theme.spacing.sm, marginTop: theme.spacing.sm }}>
              <button
                style={{ ...buttonPrimary, opacity: loading ? 0.6 : 1 }}
                onClick={handleSave}
                disabled={loading}
              >
                {loading ? "Connecting..." : "Save & Connect"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Banque Populaire connector card */}
      <div style={{ ...card, marginTop: theme.spacing.lg }}>
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          marginBottom: theme.spacing.lg,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.spacing.sm }}>
            <div style={{
              width: 44, height: 44, borderRadius: theme.radius.md,
              background: "linear-gradient(135deg, #0066b2, #00a3e0)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 13, fontWeight: 700, color: "#fff",
            }}>BP</div>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 600, color: theme.colors.textPrimary }}>
                Banque Populaire
              </h3>
              <p style={{ fontSize: 12, color: theme.colors.textMuted }}>Bank connector</p>
            </div>
          </div>

          <div style={{
            display: "flex", alignItems: "center", gap: theme.spacing.xs,
            padding: `${theme.spacing.xs}px ${theme.spacing.sm}px`,
            borderRadius: theme.radius.sm,
            background: bpWaiting2FA ? `${theme.colors.accentLavender}15`
              : bpConnected ? `${theme.colors.accentGold}15` : `${theme.colors.loss}15`,
            border: `1px solid ${bpWaiting2FA ? `${theme.colors.accentLavender}30`
              : bpConnected ? `${theme.colors.accentGold}30` : `${theme.colors.loss}30`}`,
          }}>
            {bpWaiting2FA ? (
              <Loader2 size={14} color={theme.colors.accentLavender} style={{ animation: "spin 1s linear infinite" }} />
            ) : bpConnected ? (
              <CheckCircle size={14} color={theme.colors.accentGold} />
            ) : (
              <XCircle size={14} color={theme.colors.loss} />
            )}
            <span style={{
              fontSize: 12, fontWeight: 600,
              color: bpWaiting2FA ? theme.colors.accentLavender
                : bpConnected ? theme.colors.accentGold : theme.colors.loss,
            }}>
              {bpWaiting2FA ? "Sécur'Pass" : bpConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: theme.spacing.md }}>
          {bpWaiting2FA === "app" && (
            <div style={{
              padding: theme.spacing.md,
              background: `${theme.colors.accentLavender}10`,
              border: `1px solid ${theme.colors.accentLavender}30`,
              borderRadius: theme.radius.md,
            }}>
              <p style={{ fontSize: 13, color: theme.colors.accentLavender, marginBottom: theme.spacing.sm }}>
                {bp2FAMessage || "Validez sur votre application mobile Banque Populaire"}
              </p>
              <div style={{ display: "flex", gap: theme.spacing.sm }}>
                <button style={buttonPrimary} onClick={handleBpValidate2FA}>
                  J'ai validé sur l'appli
                </button>
                <button style={buttonSecondary} onClick={handleBpReset}>
                  Annuler
                </button>
              </div>
            </div>
          )}

          {!bpWaiting2FA && (
            <>
              <div>
                <label style={labelStyle}>Identifiant</label>
                <input type="text" placeholder="Votre identifiant" value={bpLogin}
                  onChange={(e) => setBpLogin(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Mot de passe</label>
                <input type="password" placeholder="Votre mot de passe" value={bpPassword}
                  onChange={(e) => setBpPassword(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Région</label>
                <select value={bpRegion} onChange={(e) => setBpRegion(e.target.value)}
                  style={{ ...inputStyle, cursor: "pointer" }}>
                  {Object.entries(BP_REGIONS).map(([code, name]) => (
                    <option key={code} value={code}>{name}</option>
                  ))}
                </select>
              </div>
            </>
          )}

          {bpMessage && (
            <div style={{
              fontSize: 13,
              color: bpConnected ? theme.colors.accentGold
                : bpWaiting2FA ? theme.colors.accentLavender : theme.colors.loss,
            }}>
              {bpMessage}
            </div>
          )}

          {!bpWaiting2FA && (
            <div style={{ display: "flex", gap: theme.spacing.sm, marginTop: theme.spacing.sm }}>
              <button
                style={{ ...buttonPrimary, opacity: bpLoading ? 0.6 : 1 }}
                onClick={handleBpSave} disabled={bpLoading}>
                {bpLoading ? "Connexion..." : "Save & Connect"}
              </button>
            </div>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  );
};

export default Settings;
