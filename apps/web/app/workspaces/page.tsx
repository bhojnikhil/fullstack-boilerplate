"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import type { components } from "@repo/api-client";
import { api, getActiveWorkspace, setActiveWorkspace } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";

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
    void api
      .workspaces()
      .then((page) => {
        setWorkspaces(page.items);
        setWorkspaceCursor(page.next_cursor);
        setSelected(getActiveWorkspace() || "");
      })
      .catch(() => setError("Could not load workspaces."));
  }, [user, restoreSession, router]);
  useEffect(() => {
    if (!selected || !active) return;
    void api
      .members(selected)
      .then((page) => {
        setMembers(page.items);
        setMemberCursor(page.next_cursor);
      })
      .catch(() => setError("Could not load members."));
    if (admin)
      void api
        .invitations(selected)
        .then((page) => {
          setInvitations(page.items);
          setInvitationCursor(page.next_cursor);
        })
        .catch(() => setError("Could not load invitations."));
  }, [selected, active, admin]);
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
            const w = await api.createWorkspace(name);
            setWorkspaces((v) => [w, ...v]);
            setActiveWorkspace(w.id);
            setSelected(w.id);
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
              onClick={() => {
                setActiveWorkspace(w.id);
                setSelected(w.id);
                setLink("");
                setQr("");
              }}
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
        <>
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
                    onClick={() =>
                      void run(async () => {
                        await api.changeRole(
                          selected,
                          m.user_id,
                          m.role === "admin" ? "member" : "admin",
                        );
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
                    onClick={() =>
                      void run(async () => {
                        await api.removeMember(selected, m.user_id);
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
                      setInvitations((v) => [invitation, ...v]);
                      setLink(invitation.link || "");
                      setQr(
                        invitation.link ? await QRCode.toDataURL(invitation.link) : "",
                      );
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
                      onClick={() =>
                        void run(async () => {
                          await api.revokeInvitation(selected, i.id);
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
        </>
      )}
    </div>
  );
}
