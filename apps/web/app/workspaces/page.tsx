"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import type { components } from "@repo/api-client";
import { api, ApiError, getActiveWorkspace, setActiveWorkspace } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { FormError, TextField } from "@/components/form";
import { GoogleReauthenticate } from "@/components/google-reauthenticate";
import { Button } from "@/components/ui/button";

// ISO 4217 currencies accepted by the workspace API; update with ISO amendments.
const CURRENCIES =
  `AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWG`.split(
    " ",
  );
type Workspace = components["schemas"]["WorkspaceResponse"];
type Member = components["schemas"]["MemberResponse"];
type Invitation = components["schemas"]["InvitationResponse"];
export default function WorkspacesPage() {
  const router = useRouter();
  const { user, restoreSession } = useAuthStore();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceCursor, setWorkspaceCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState("");
  const [members, setMembers] = useState<Member[]>([]);
  const [memberCursor, setMemberCursor] = useState<string | null>(null);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [invitationCursor, setInvitationCursor] = useState<string | null>(null);
  const selectedRef = useRef("");
  const [currency, setCurrency] = useState("USD");
  const [timezone, setTimezone] = useState("UTC");
  const [rename, setRename] = useState("");
  const [ownershipPassword, setOwnershipPassword] = useState("");
  const [transferTo, setTransferTo] = useState("");
  const [verified, setVerified] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const [link, setLink] = useState("");
  const [qr, setQr] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [failures, setFailures] = useState(0);
  const [busy, setBusy] = useState(false);
  const active = workspaces.find((w) => w.id === selected);
  const admin = active?.role === "owner" || active?.role === "admin";
  function selectWorkspace(id: string) {
    selectedRef.current = id;
    setMembers([]);
    setMemberCursor(null);
    setInvitations([]);
    setInvitationCursor(null);
    setLink("");
    setQr("");
    setRename("");
    setTransferTo("");
    setOwnershipPassword("");
    setVerified(false);
    setSelected(id);
    setActiveWorkspace(id || null);
  }
  async function confirmOwnership() {
    if (user?.sign_in_methods.includes("password")) {
      try {
        await api.reauthenticate({ password: ownershipPassword });
      } finally {
        setOwnershipPassword("");
      }
    } else if (!verified) throw new Error("Verify your identity with Google first.");
  }
  async function run(action: () => Promise<void>, success = "") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
    } catch {
      setError("The request failed. Please check your details and try again.");
      setFailures((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!user) {
      void restoreSession()
        .then((ok) => {
          if (!ok) router.push("/auth/login");
        })
        .catch(() => setError("Could not restore your session."));
      return;
    }
    let alive = true;
    void api
      .workspaces()
      .then(async (page) => {
        if (!alive) return;
        setWorkspaces(page.items);
        setWorkspaceCursor(page.next_cursor);
        const id = getActiveWorkspace();
        if (!id) return;
        let current = page.items.find((w) => w.id === id);
        if (!current) {
          try {
            current = await api.workspace(id);
            if (!alive) return;
            setWorkspaces((v) => [...v, current!]);
          } catch (err) {
            if (!alive) return;
            if (err instanceof ApiError && err.status === 404) {
              setActiveWorkspace(null);
              return;
            }
            throw err;
          }
        }
        selectedRef.current = id;
        setSelected(id);
      })
      .catch(() => {
        if (alive) setError("Could not load workspaces.");
      });
    return () => {
      alive = false;
    };
  }, [user, restoreSession, router]);
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (!event.key?.startsWith("workspace:")) return;
      const id = getActiveWorkspace();
      if (id === selectedRef.current) return;
      selectedRef.current = "";
      setSelected("");
      setMembers([]);
      setMemberCursor(null);
      setInvitations([]);
      setInvitationCursor(null);
      setLink("");
      setQr("");
      setRename("");
      setTransferTo("");
      setOwnershipPassword("");
      setVerified(false);
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  useEffect(() => {
    if (!selected || !active) return;
    let alive = true;
    void api
      .members(selected)
      .then((page) => {
        if (alive && selectedRef.current === selected) {
          setMembers(page.items);
          setMemberCursor(page.next_cursor);
        }
      })
      .catch(() => {
        if (alive && selectedRef.current === selected)
          setError("Could not load members.");
      });
    if (admin)
      void api
        .invitations(selected)
        .then((page) => {
          if (alive && selectedRef.current === selected) {
            setInvitations(page.items);
            setInvitationCursor(page.next_cursor);
          }
        })
        .catch(() => {
          if (alive && selectedRef.current === selected)
            setError("Could not load invitations.");
        });
    return () => {
      alive = false;
    };
  }, [selected, active?.id, active?.role, admin]);

  if (!user) return error ? <p role="alert">{error}</p> : null;
  return (
    <div className="mx-auto grid max-w-2xl gap-7">
      <h1 className="text-3xl font-semibold">Workspaces</h1>
      <FormError message={error} failureCount={failures} />
      {notice && <p role="status">{notice}</p>}
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            const w = await api.createWorkspace(name, currency, timezone);
            setWorkspaces((v) => [w, ...v]);
            selectWorkspace(w.id);
            setName("");
          }, "Workspace created.");
        }}
      >
        <h2 className="text-xl font-semibold">Create workspace</h2>
        <TextField
          label="Workspace name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <label htmlFor="currency">Currency</label>
        <select
          id="currency"
          className="rounded-md border bg-background p-2"
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
        >
          {CURRENCIES.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
        <label htmlFor="timezone">Time zone</label>
        <select
          id="timezone"
          className="rounded-md border bg-background p-2"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
        >
          <option value="UTC">UTC</option>
          {Intl.supportedValuesOf("timeZone")
            .filter((zone) => zone !== "UTC")
            .map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
        </select>
        <Button disabled={busy}>Create workspace</Button>
      </form>
      <section className="grid gap-3">
        <h2 className="text-xl font-semibold">Your workspaces</h2>
        {workspaces.map((w) => (
          <div key={w.id} className="flex items-center justify-between gap-3">
            <span>
              {w.name} ({w.role}){selected === w.id ? " — active" : ""}
            </span>
            <Button
              variant="secondary"
              aria-label={`Switch to ${w.name}`}
              disabled={busy}
              onClick={() => selectWorkspace(w.id)}
            >
              Switch
            </Button>
          </div>
        ))}
        {workspaceCursor && (
          <Button
            variant="secondary"
            onClick={() =>
              void run(async () => {
                const page = await api.workspaces(workspaceCursor);
                setWorkspaces((v) => [...v, ...page.items]);
                setWorkspaceCursor(page.next_cursor);
              })
            }
          >
            Load more workspaces
          </Button>
        )}
        {selected && (
          <Link className="underline" href="/items">
            Open items
          </Link>
        )}
      </section>
      {active && (
        <div key={selected} className="grid gap-7">
          <section className="grid gap-3">
            <h2 className="text-xl font-semibold">Manage {active.name}</h2>
            {admin && (
              <form
                className="grid gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void run(async () => {
                    const w = await api.renameWorkspace(selected, rename);
                    setWorkspaces((v) => v.map((x) => (x.id === w.id ? w : x)));
                    setRename("");
                  }, "Workspace renamed.");
                }}
              >
                <TextField
                  label="New workspace name"
                  value={rename}
                  onChange={(e) => setRename(e.target.value)}
                  required
                />
                <Button disabled={busy}>Rename workspace</Button>
              </form>
            )}
            {active.role !== "owner" && (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => {
                  if (window.confirm(`Leave ${active.name}?`))
                    void run(async () => {
                      await api.leaveWorkspace(selected);
                      setWorkspaces((v) => v.filter((w) => w.id !== selected));
                      selectWorkspace("");
                    }, "Workspace left.");
                }}
              >
                Leave {active.name}
              </Button>
            )}
            {active.role === "owner" && (
              <>
                {user.sign_in_methods.includes("password") ? (
                  <TextField
                    label="Password for ownership changes"
                    type="password"
                    autoComplete="current-password"
                    value={ownershipPassword}
                    onChange={(e) => setOwnershipPassword(e.target.value)}
                  />
                ) : (
                  <>
                    <GoogleReauthenticate onVerified={() => setVerified(true)} />
                    {verified && <p role="status">Identity verified.</p>}
                    <p>
                      You can also{" "}
                      <Link href="/auth/forgot-password" className="underline">
                        recover your password
                      </Link>
                      .
                    </p>
                  </>
                )}
                <label htmlFor="transfer">Transfer ownership to</label>
                <select
                  id="transfer"
                  className="rounded-md border bg-background p-2"
                  value={transferTo}
                  onChange={(e) => setTransferTo(e.target.value)}
                >
                  <option value="">Choose a member</option>
                  {members
                    .filter((m) => m.user_id !== user.id)
                    .map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.name}
                      </option>
                    ))}
                </select>
                <Button
                  disabled={
                    busy ||
                    !transferTo ||
                    (!user.sign_in_methods.includes("password") && !verified)
                  }
                  onClick={() => {
                    if (window.confirm("Transfer ownership?"))
                      void run(async () => {
                        await confirmOwnership();
                        await api.transferWorkspace(selected, transferTo);
                        setVerified(false);
                        const w = await api.workspace(selected);
                        setWorkspaces((v) => v.map((x) => (x.id === w.id ? w : x)));
                      }, "Ownership transferred.");
                  }}
                >
                  Transfer ownership
                </Button>
                <Button
                  variant="destructive"
                  disabled={
                    busy || (!user.sign_in_methods.includes("password") && !verified)
                  }
                  onClick={() => {
                    if (window.confirm(`Permanently delete ${active.name}?`))
                      void run(async () => {
                        await confirmOwnership();
                        await api.deleteWorkspace(selected);
                        setWorkspaces((v) => v.filter((w) => w.id !== selected));
                        selectWorkspace("");
                      }, "Workspace deleted.");
                  }}
                >
                  Delete {active.name}
                </Button>
              </>
            )}
          </section>
          <section className="grid gap-3">
            <h2 className="text-xl font-semibold">Members of {active.name}</h2>
            {members.map((m) => (
              <div key={m.user_id} className="flex flex-wrap items-center gap-2">
                <span>
                  {m.name} {m.email && `(${m.email})`} — {m.role}
                </span>
                {active.role === "owner" && m.role !== "owner" && (
                  <Button
                    variant="secondary"
                    disabled={busy}
                    aria-label={`Make ${m.name} ${m.role === "admin" ? "member" : "admin"}`}
                    onClick={() =>
                      void run(async () => {
                        await api.changeRole(
                          selected,
                          m.user_id,
                          m.role === "admin" ? "member" : "admin",
                        );
                        if (selectedRef.current !== selected) return;
                        setMembers((v) =>
                          v.map((x) =>
                            x.user_id === m.user_id
                              ? { ...x, role: m.role === "admin" ? "member" : "admin" }
                              : x,
                          ),
                        );
                      }, "Role updated.")
                    }
                  >
                    Make {m.role === "admin" ? "member" : "admin"}
                  </Button>
                )}
                {admin && m.role !== "owner" && m.user_id !== user.id && (
                  <Button
                    variant="secondary"
                    disabled={busy}
                    aria-label={`Remove ${m.name}`}
                    onClick={() =>
                      void run(async () => {
                        await api.removeMember(selected, m.user_id);
                        if (selectedRef.current !== selected) return;
                        setMembers((v) => v.filter((x) => x.user_id !== m.user_id));
                      }, "Member removed.")
                    }
                  >
                    Remove
                  </Button>
                )}
              </div>
            ))}
            {memberCursor && (
              <Button
                variant="secondary"
                onClick={() =>
                  void run(async () => {
                    const page = await api.members(selected, memberCursor);
                    if (selectedRef.current !== selected) return;
                    setMembers((v) => [...v, ...page.items]);
                    setMemberCursor(page.next_cursor);
                  })
                }
              >
                Load more members
              </Button>
            )}
          </section>
          {admin && (
            <section className="grid gap-3">
              <h2 className="text-xl font-semibold">Invitations</h2>
              <form
                className="grid gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void run(
                    async () => {
                      const invitation = await api.createInvitation(
                        selected,
                        role,
                        email,
                      );
                      if (selectedRef.current !== selected) return;
                      const qrCode = invitation.link
                        ? await QRCode.toDataURL(invitation.link)
                        : "";
                      if (selectedRef.current !== selected) return;
                      setInvitations((v) => [invitation, ...v]);
                      setLink(invitation.link || "");
                      setQr(qrCode);
                    },
                    email
                      ? "Invitation sent."
                      : "Invitation link created. Copy it now; it will not be shown again.",
                  );
                }}
              >
                <TextField
                  label="Invite email (optional)"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <label htmlFor="role">Invitation role</label>
                <select
                  className="rounded-md border bg-background p-2"
                  id="role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as "admin" | "member")}
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
                <Button disabled={busy}>Create invitation</Button>
              </form>
              {link && (
                <div className="break-all">
                  <p>
                    Share this link:{" "}
                    <a className="underline" href={link}>
                      {link}
                    </a>
                  </p>
                  {qr && (
                    <img src={qr} alt="Invitation QR code" width="200" height="200" />
                  )}
                </div>
              )}
              {invitations.map((i) => (
                <div className="flex flex-wrap items-center gap-2" key={i.id}>
                  <span>
                    {i.email || "Shareable link"} — {i.role}, {i.status}
                  </span>
                  {i.status === "pending" && (
                    <Button
                      variant="secondary"
                      disabled={busy}
                      aria-label={`Revoke invitation for ${i.email || i.id}`}
                      onClick={() =>
                        void run(async () => {
                          await api.revokeInvitation(selected, i.id);
                          if (selectedRef.current !== selected) return;
                          setInvitations((v) =>
                            v.map((x) =>
                              x.id === i.id ? { ...x, status: "revoked" } : x,
                            ),
                          );
                        }, "Invitation revoked.")
                      }
                    >
                      Revoke
                    </Button>
                  )}
                </div>
              ))}
              {invitationCursor && (
                <Button
                  variant="secondary"
                  onClick={() =>
                    void run(async () => {
                      const page = await api.invitations(selected, invitationCursor);
                      if (selectedRef.current !== selected) return;
                      setInvitations((v) => [...v, ...page.items]);
                      setInvitationCursor(page.next_cursor);
                    })
                  }
                >
                  Load more invitations
                </Button>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
