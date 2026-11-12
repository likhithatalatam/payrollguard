import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Users,
  Wallet,
  AlertTriangle,
  RefreshCw,
  Download,
  ShieldCheck,
  Activity,
  CheckCircle,
  XCircle,
  ClipboardList,
  History,
  Search,
} from "lucide-react";

const API = "http://127.0.0.1:8000/api";

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed (${response.status})`);
  }

  return response.json();
}

function App() {
  const [dashboard, setDashboard] = useState({});
  const [periods, setPeriods] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [payroll, setPayroll] = useState([]);
  const [pendingEntries, setPendingEntries] = useState([]);
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const [page, setPage] = useState("Overview");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const [auditEntityType, setAuditEntityType] = useState("TIME_ENTRY");
  const [auditEntityId, setAuditEntityId] = useState("");
  const [auditHistory, setAuditHistory] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);

  async function loadInitialData() {
    try {
      const [dash, periodData, employeeData] = await Promise.all([
        request("/dashboard"),
        request("/periods"),
        request("/employees"),
      ]);

      setDashboard(dash);
      setPeriods(periodData);
      setEmployees(employeeData);

      if (!selectedPeriod && periodData.length > 0) {
        setSelectedPeriod(periodData[0].pay_period_id);
      }
    } catch (error) {
      setMessage("Could not connect to backend: " + error.message);
    }
  }

  async function loadPeriodData(period) {
    if (!period) return;

    try {
      const [payrollData, exceptionData, pendingData] = await Promise.all([
        request(`/payroll/${period}`),
        request(`/exceptions/${period}`),
        request(`/time-entries/pending/${period}`),
      ]);

      setPayroll(payrollData);
      setExceptions(exceptionData);
      setPendingEntries(pendingData);
    } catch (error) {
      setPayroll([]);
      setExceptions([]);
      setPendingEntries([]);
      setMessage("Period data: " + error.message);
    }
  }

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    loadPeriodData(selectedPeriod);
  }, [selectedPeriod]);

  async function refreshData() {
    await loadInitialData();
    await loadPeriodData(selectedPeriod);
  }

  async function runPayroll() {
    if (!selectedPeriod) return;

    setLoading(true);
    setMessage("");

    try {
      const result = await request(`/payroll/run/${selectedPeriod}`, {
        method: "POST",
      });

      setMessage(result.message || "Payroll processed successfully.");
      await refreshData();
    } catch (error) {
      setMessage("Payroll failed: " + error.message);
    } finally {
      setLoading(false);
    }
  }

  async function exportPayroll() {
    try {
      const response = await fetch(`${API}/payroll/export/${selectedPeriod}`);

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download = `payroll-${selectedPeriod}.csv`;
      link.click();

      URL.revokeObjectURL(url);
      setMessage("Payroll CSV exported successfully.");
    } catch (error) {
      setMessage("Export failed: " + error.message);
    }
  }

  async function decideTimeEntry(entryId, decision) {
    const confirmed = window.confirm(
      `Are you sure you want to ${decision.toLowerCase()} this time entry?`,
    );

    if (!confirmed) return;

    setLoading(true);
    setMessage("");

    try {
      const result = await request(`/time-entries/${entryId}/decision`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          actor_role: "MANAGER",
          actor_id: "MANAGER-001",
        }),
      });

      setMessage(result.message || `Time entry ${decision.toLowerCase()}.`);
      await refreshData();
    } catch (error) {
      setMessage("Time-entry decision failed: " + error.message);
    } finally {
      setLoading(false);
    }
  }

  async function resolveException(exceptionId) {
    const note = window.prompt(
      "Enter the resolution note. Resolve only after the underlying issue has been corrected:",
    );

    if (note === null) return;

    if (!note.trim()) {
      setMessage("A resolution note is required.");
      return;
    }

    setLoading(true);
    setMessage("");

    try {
      const result = await request(`/exceptions/${exceptionId}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          actor_role: "HR",
          actor_id: "HR-001",
          resolution_note: note.trim(),
        }),
      });

      setMessage(result.message || "Exception resolved successfully.");
      await refreshData();
    } catch (error) {
      setMessage("Exception resolution failed: " + error.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadAuditHistory() {
    if (!auditEntityId.trim()) {
      setMessage("Enter an entity ID to search audit history.");
      return;
    }

    setAuditLoading(true);
    setAuditHistory([]);
    setMessage("");

    try {
      const result = await request(
        `/audit/${encodeURIComponent(auditEntityType)}/${encodeURIComponent(auditEntityId.trim())}`,
      );

      setAuditHistory(Array.isArray(result) ? result : result.events || []);
      if (!Array.isArray(result) && !result.events) {
        setMessage("Unexpected audit response format.");
      }
    } catch (error) {
      setMessage("Could not load audit history: " + error.message);
    } finally {
      setAuditLoading(false);
    }
  }

  const stats = [
    {
      label: "Employees",
      value: dashboard.total_employees ?? 0,
      icon: Users,
    },
    {
      label: "Pay Periods",
      value: dashboard.total_pay_periods ?? 0,
      icon: Wallet,
    },
    {
      label: "Payroll Records",
      value: dashboard.total_payroll_records ?? 0,
      icon: Activity,
    },
    {
      label: "Open Exceptions",
      value: dashboard.open_exceptions ?? 0,
      icon: AlertTriangle,
    },
  ];

  const navigation = [
    ["Overview", LayoutDashboard],
    ["Employees", Users],
    ["Payroll", Wallet],
    ["Approvals", ClipboardList],
    ["Exceptions", AlertTriangle],
    ["Reconciliation", Activity],
    ["Audit History", History],
  ];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <ShieldCheck size={30} />
          <div>
            <h2>PayrollGuard</h2>
            <span>AI PAYROLL CONTROL</span>
          </div>
        </div>

        <p className="nav-heading">WORKSPACE</p>

        {navigation.map(([name, Icon]) => (
          <button
            key={name}
            className={`nav-item ${page === name ? "active" : ""}`}
            onClick={() => setPage(name)}
          >
            <Icon size={19} />
            {name}
          </button>
        ))}

        <div className="sidebar-footer">
          <ShieldCheck size={18} />
          <span>Payroll validation system</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{page}</h1>
            <p>Payroll operations and validation center</p>
          </div>

          <div className="top-actions">
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
            >
              {periods.map((period) => (
                <option key={period.pay_period_id} value={period.pay_period_id}>
                  {period.pay_period_id}
                </option>
              ))}
            </select>

            <button className="run-btn" onClick={runPayroll} disabled={loading}>
              <RefreshCw size={16} />
              {loading ? "Processing..." : "Run Payroll"}
            </button>
          </div>
        </header>

        {message && (
          <div className="message">
            <span>{message}</span>
            <button onClick={() => setMessage("")}>×</button>
          </div>
        )}

        {page === "Overview" && (
          <>
            <section className="welcome">
              <div>
                <span className="eyebrow">PAYROLL INTELLIGENCE</span>
                <h2>Welcome to PayrollGuard AI</h2>
                <p>
                  Validate payroll inputs, identify errors, and improve payroll
                  accuracy with traceable checks.
                </p>
              </div>
              <ShieldCheck size={65} />
            </section>

            <section className="stats-grid">
              {stats.map((stat) => {
                const Icon = stat.icon;
                return (
                  <div className="stat-card" key={stat.label}>
                    <div className="stat-icon">
                      <Icon size={22} />
                    </div>
                    <p>{stat.label}</p>
                    <h2>{stat.value}</h2>
                  </div>
                );
              })}
            </section>

            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Payroll processing</h2>
                  <p>Selected pay period: {selectedPeriod || "Loading..."}</p>
                </div>
                <button className="secondary-btn" onClick={exportPayroll}>
                  <Download size={16} />
                  Export CSV
                </button>
              </div>

              <div className="quick-info">
                <div>
                  <span>Payroll records</span>
                  <strong>{payroll.length}</strong>
                </div>
                <div>
                  <span>Exceptions found</span>
                  <strong>{exceptions.length}</strong>
                </div>
                <div>
                  <span>Pending approvals</span>
                  <strong>{pendingEntries.length}</strong>
                </div>
              </div>
            </section>
          </>
        )}

        {page === "Employees" && (
          <section className="panel">
            <h2>Employee Directory</h2>
            <p>Employee records from the payroll database.</p>
            <DataTable
              headers={["Employee ID", "First Name", "Last Name", "Status"]}
              rows={employees.map((e) => [
                e.employee_id,
                e.first_name,
                e.last_name,
                e.employment_status,
              ])}
            />
          </section>
        )}

        {page === "Payroll" && (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Payroll Records</h2>
                <p>Calculated payroll for the selected period.</p>
              </div>
              <button className="secondary-btn" onClick={exportPayroll}>
                <Download size={16} /> Export CSV
              </button>
            </div>
            <DataTable
              headers={[
                "Employee ID",
                "Base Pay",
                "Gross Pay",
                "Deductions",
                "Net Pay",
                "Status",
              ]}
              rows={payroll.map((p) => [
                p.employee_id,
                p.base_pay,
                p.gross_pay,
                p.deductions_total,
                p.net_pay,
                p.status,
              ])}
            />
          </section>
        )}

        {page === "Approvals" && (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Pending Time Entries</h2>
                <p>
                  Review time entries before they are included in payroll.
                  Showing up to 100 pending records.
                </p>
              </div>
              <span className="count-label">
                {pendingEntries.length} pending
              </span>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Entry ID</th>
                    <th>Employee</th>
                    <th>Work Date</th>
                    <th>Hours</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingEntries.length === 0 ? (
                    <tr>
                      <td colSpan="6">No pending time entries found.</td>
                    </tr>
                  ) : (
                    pendingEntries.map((entry) => (
                      <tr key={entry.entry_id}>
                        <td>{entry.entry_id}</td>
                        <td>{entry.employee_id}</td>
                        <td>{entry.work_date}</td>
                        <td>{entry.hours}</td>
                        <td>
                          <span className="status-pill pending">
                            {entry.status}
                          </span>
                        </td>
                        <td>
                          <div className="action-group">
                            <button
                              className="action-btn approve"
                              disabled={loading}
                              onClick={() =>
                                decideTimeEntry(entry.entry_id, "APPROVED")
                              }
                            >
                              <CheckCircle size={14} /> Approve
                            </button>
                            <button
                              className="action-btn reject"
                              disabled={loading}
                              onClick={() =>
                                decideTimeEntry(entry.entry_id, "REJECTED")
                              }
                            >
                              <XCircle size={14} /> Reject
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {page === "Exceptions" && (
          <section className="panel">
            <h2>Validation Exceptions</h2>
            <p>
              Review issues detected during payroll validation. Only open
              exceptions can be manually resolved.
            </p>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Exception ID</th>
                    <th>Employee</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Description</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {exceptions.length === 0 ? (
                    <tr>
                      <td colSpan="6">No exceptions found.</td>
                    </tr>
                  ) : (
                    exceptions.slice(0, 100).map((e) => (
                      <tr key={e.exception_id}>
                        <td>{e.exception_id}</td>
                        <td>{e.employee_id}</td>
                        <td>{e.severity}</td>
                        <td>
                          <span
                            className={`status-pill ${e.status?.toLowerCase()}`}
                          >
                            {e.status}
                          </span>
                        </td>
                        <td className="description-cell">{e.description}</td>
                        <td>
                          {e.status === "OPEN" ? (
                            <button
                              className="action-btn resolve"
                              disabled={loading}
                              onClick={() => resolveException(e.exception_id)}
                            >
                              <CheckCircle size={14} /> Resolve
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <p className="table-note">Showing up to 100 exceptions.</p>
          </section>
        )}

        {page === "Reconciliation" && (
          <section className="panel">
            <h2>Payroll Reconciliation</h2>
            <p>Compare payroll totals and identify calculation differences.</p>
            <Reconciliation period={selectedPeriod} />
          </section>
        )}

        {page === "Audit History" && (
          <section className="panel">
            <h2>Audit History</h2>
            <p>Search the recorded actions for a time entry or exception.</p>

            <div className="audit-search">
              <select
                value={auditEntityType}
                onChange={(e) => setAuditEntityType(e.target.value)}
              >
                <option value="TIME_ENTRY">Time Entry</option>
                <option value="EXCEPTION">Exception</option>
                <option value="PAY_PERIOD">Pay Period</option>
              </select>

              <input
                value={auditEntityId}
                onChange={(e) => setAuditEntityId(e.target.value)}
                placeholder="Enter entity ID"
              />

              <button
                className="run-btn"
                onClick={loadAuditHistory}
                disabled={auditLoading}
              >
                <Search size={15} />
                {auditLoading ? "Searching..." : "Search History"}
              </button>
            </div>

            <DataTable
              headers={[
                "Event ID",
                "Action",
                "Actor Role",
                "Actor ID",
                "Old Value",
                "New Value",
                "Created At",
              ]}
              rows={auditHistory.map((event) => [
                event.event_id,
                event.action,
                event.actor_role,
                event.actor_id,
                event.old_value == null
                  ? "—"
                  : typeof event.old_value === "object"
                    ? JSON.stringify(event.old_value)
                    : event.old_value,

                event.new_value == null
                  ? "—"
                  : typeof event.new_value === "object"
                    ? JSON.stringify(event.new_value)
                    : event.new_value,
                event.created_at,
              ])}
            />
          </section>
        )}

        <footer>
          PayrollGuard AI · Payroll validation and reconciliation platform
        </footer>
      </main>
    </div>
  );
}

function DataTable({ headers, rows }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length}>No records available.</td>
            </tr>
          ) : (
            rows.slice(0, 100).map((row, index) => (
              <tr key={index}>
                {row.map((cell, i) => (
                  <td key={i}>{cell ?? "—"}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
      <p className="table-note">Showing up to 100 records.</p>
    </div>
  );
}

function Reconciliation({ period }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!period) return;

    setData(null);
    setError("");

    fetch(`${API}/reconciliation/${period}`)
      .then((response) => {
        if (!response.ok) throw new Error("Could not load reconciliation.");
        return response.json();
      })
      .then(setData)
      .catch((err) => setError(err.message));
  }, [period]);

  if (error) return <p>{error}</p>;
  if (!data) return <p>Loading reconciliation...</p>;

  return (
    <div className="quick-info">
      {Object.entries(data).map(([key, value]) => (
        <div key={key}>
          <span>{key.replaceAll("_", " ")}</span>
          <strong>
            {typeof value === "number" ? value.toLocaleString() : String(value)}
          </strong>
        </div>
      ))}
    </div>
  );
}

export default App;
