const pageDataset = document.body.dataset;

const elements = {
  statusBanner: document.querySelector("#status-banner"),
  workspaceBadge: document.querySelector("#workspace-badge"),
  currentUserBadge: document.querySelector("#current-user-badge"),
  refreshWorkspaceButton: document.querySelector("#refresh-workspace"),
  logoutButton: document.querySelector("#logout"),
  projectList: document.querySelector("#project-list"),
  projectForm: document.querySelector("#project-form"),
  deleteProjectButton: document.querySelector("#delete-project"),
  exportProjectButton: document.querySelector("#export-selected-project"),
  permitForm: document.querySelector("#permit-form"),
  permitList: document.querySelector("#permit-list"),
  permitImportFile: document.querySelector("#permit-import-file"),
  importPermitsButton: document.querySelector("#import-permits"),
  changeEventForm: document.querySelector("#change-event-form"),
  changeEventList: document.querySelector("#change-event-list"),
  rfqForm: document.querySelector("#rfq-form"),
  quoteForm: document.querySelector("#quote-form"),
  changeOrderForm: document.querySelector("#change-order-form"),
  changeOrderList: document.querySelector("#change-order-list"),
  workflowTitle: document.querySelector("#workflow-title"),
  workflowSummary: document.querySelector("#workflow-summary"),
  ownerPackagePreview: document.querySelector("#owner-package-preview"),
  submitSelectedApprovalButton: document.querySelector("#submit-selected-approval"),
  downloadOwnerPackageButton: document.querySelector("#download-owner-package"),
  userForm: document.querySelector("#user-form"),
  userList: document.querySelector("#user-list"),
  adminPanel: document.querySelector("#admin-panel"),
  adminStatus: document.querySelector("#admin-status"),
  activityList: document.querySelector("#activity-list"),
  projectName: document.querySelector("#project-name"),
  projectSubtitle: document.querySelector("#project-subtitle"),
  projectNotes: document.querySelector("#project-notes"),
  metricProjects: document.querySelector("#metric-projects"),
  metricPermitsRisk: document.querySelector("#metric-permits-risk"),
  metricApprovals: document.querySelector("#metric-approvals"),
  metricCost: document.querySelector("#metric-cost"),
  metricSchedule: document.querySelector("#metric-schedule"),
  metricNotifications: document.querySelector("#metric-notifications"),
  selectedProjectPermits: document.querySelector("#selected-project-permits"),
  selectedProjectEvents: document.querySelector("#selected-project-events"),
  selectedProjectPending: document.querySelector("#selected-project-pending"),
  selectedProjectCost: document.querySelector("#selected-project-cost"),
  downloadPermitTemplate: document.querySelector("#download-permit-template"),
  downloadChangeEventTemplate: document.querySelector("#download-change-event-template"),
};

const state = {
  session: {
    authRequired: pageDataset.authRequired === "true",
    authenticated: pageDataset.authRequired !== "true",
    canWrite: pageDataset.canWrite === "true",
    canManageUsers: pageDataset.canManageUsers === "true",
    canApproveFinancials: pageDataset.canApproveFinancials === "true",
    csrfToken: pageDataset.csrfToken || "",
    username: pageDataset.currentUser || "",
    role: pageDataset.currentRole || "",
  },
  workspace: {
    name: pageDataset.workspaceName || "Open workspace",
  },
  dashboard: null,
  projects: [],
  selectedProject: null,
  selectedChangeEventId: null,
  selectedChangeOrderId: null,
  users: [],
  activity: [],
};

function setStatus(message, tone = "info") {
  elements.statusBanner.textContent = message;
  elements.statusBanner.dataset.tone = tone;
}

function formatErrorDetail(detail) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.join("; ");
  }
  if (detail && typeof detail === "object" && Array.isArray(detail.errors)) {
    return detail.errors.join(" | ");
  }
  return "Request failed";
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value || 0);
}

function formatDate(value) {
  if (!value) {
    return "Not set";
  }
  return new Date(value).toLocaleDateString();
}

function formatDateTime(value) {
  if (!value) {
    return "Unknown";
  }
  return new Date(value).toLocaleString();
}

function slug(text) {
  return (text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

async function apiRequest(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };

  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && state.session.csrfToken) {
    headers["X-CSRF-Token"] = state.session.csrfToken;
  }

  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers,
  });

  if (response.status === 401) {
    window.location.assign("/login?next=%2F");
    throw new Error("Authentication required");
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null ? payload.detail || payload : payload;
    throw new Error(formatErrorDetail(detail));
  }
  return payload;
}

function resetProjectDetails() {
  state.selectedProject = null;
  state.selectedChangeEventId = null;
  state.selectedChangeOrderId = null;
  elements.projectName.textContent = "No project selected";
  elements.projectSubtitle.textContent = "Pick a project to manage permits, scope drift, and approvals.";
  elements.projectNotes.textContent = "Project notes will appear here when a project is selected.";
  elements.selectedProjectPermits.textContent = "0";
  elements.selectedProjectEvents.textContent = "0";
  elements.selectedProjectPending.textContent = "0";
  elements.selectedProjectCost.textContent = formatCurrency(0);
  elements.permitList.className = "site-list empty-state";
  elements.permitList.textContent = "Select a project to view permits.";
  elements.changeEventList.className = "site-list empty-state";
  elements.changeEventList.textContent = "Select a project to view change events.";
  elements.changeOrderList.className = "site-list empty-state";
  elements.changeOrderList.textContent = "Create or select a change event to see packaged change orders.";
  elements.workflowTitle.textContent = "No change event selected";
  elements.workflowSummary.className = "empty-state";
  elements.workflowSummary.textContent = "Select a change event to create RFQs, quotes, and change orders.";
  elements.ownerPackagePreview.textContent = "Owner package preview will appear here.";
}

function currentChangeEvent() {
  if (!state.selectedProject) {
    return null;
  }
  return state.selectedProject.change_events.find((event) => event.id === state.selectedChangeEventId) || null;
}

function currentChangeOrder() {
  const event = currentChangeEvent();
  if (!event) {
    return null;
  }
  return event.change_orders.find((item) => item.id === state.selectedChangeOrderId) || event.change_orders[0] || null;
}

function canActOnApproval(step) {
  if (!state.session.canWrite) {
    return false;
  }
  return state.session.canManageUsers || state.session.role === step.role_required;
}

function applySessionState() {
  elements.workspaceBadge.textContent = state.workspace.name || "Open workspace";
  if (state.session.authRequired) {
    elements.currentUserBadge.textContent = state.session.username
      ? `Signed in as ${state.session.username} (${state.session.role}).`
      : "Secure workspace";
  } else {
    elements.currentUserBadge.textContent = "Local workspace mode.";
  }

  const canWrite = state.session.canWrite;
  [elements.projectForm, elements.permitForm, elements.changeEventForm, elements.rfqForm, elements.quoteForm, elements.changeOrderForm]
    .filter(Boolean)
    .forEach((form) => {
      form.classList.toggle("disabled-stack", !canWrite);
      form.querySelectorAll("input, textarea, select, button").forEach((field) => {
        field.disabled = !canWrite;
      });
    });

  elements.importPermitsButton.disabled = !canWrite || !state.selectedProject;
  elements.deleteProjectButton.disabled = !canWrite || !state.selectedProject;
  elements.exportProjectButton.disabled = !state.selectedProject;
  elements.submitSelectedApprovalButton.disabled = !canWrite || !currentChangeOrder();
  elements.downloadOwnerPackageButton.disabled = !currentChangeOrder();
  elements.adminPanel.hidden = !state.session.canManageUsers;
  elements.adminStatus.textContent = state.session.canManageUsers
    ? "Manage workspace admins, PMs, engineers, finance approvers, and viewers."
    : "Admin access is required to manage workspace users.";
}

function renderDashboard() {
  const dashboard = state.dashboard || {
    active_projects: 0,
    permits_at_risk: 0,
    pending_approvals: 0,
    at_risk_cost_usd: 0,
    schedule_slip_days: 0,
    notification_backlog: 0,
  };
  elements.metricProjects.textContent = String(dashboard.active_projects);
  elements.metricPermitsRisk.textContent = String(dashboard.permits_at_risk);
  elements.metricApprovals.textContent = String(dashboard.pending_approvals);
  elements.metricCost.textContent = formatCurrency(dashboard.at_risk_cost_usd);
  elements.metricSchedule.textContent = `${dashboard.schedule_slip_days} days`;
  elements.metricNotifications.textContent = String(dashboard.notification_backlog);
}

function renderProjects() {
  if (!state.projects.length) {
    elements.projectList.className = "project-list empty-state";
    elements.projectList.textContent = "No projects yet. Create your first commercial job to start tracking permits and change exposure.";
    return;
  }

  elements.projectList.className = "project-list";
  elements.projectList.innerHTML = state.projects
    .map((project) => {
      const selected = state.selectedProject && state.selectedProject.id === project.id;
      return `
        <button class="project-card ${selected ? "selected" : ""}" data-project-id="${project.id}" type="button">
          <span class="pill">${project.status}</span>
          <strong>${project.name}</strong>
          <span class="muted-text">${project.project_code} · ${project.client_name}</span>
          <span class="muted-text">${project.location} · ${project.sector.replaceAll("_", " ")}</span>
          <span class="muted-text">${project.permit_count} permits · ${project.change_event_count} events · ${project.pending_change_order_count} pending COs</span>
          <span class="muted-text">At-risk cost: ${formatCurrency(project.at_risk_cost_usd)}</span>
        </button>
      `;
    })
    .join("");

  elements.projectList.querySelectorAll("[data-project-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      await loadProject(button.dataset.projectId);
    });
  });
}

function renderSelectedProject() {
  if (!state.selectedProject) {
    resetProjectDetails();
    applySessionState();
    return;
  }

  const project = state.selectedProject;
  elements.projectName.textContent = project.name;
  elements.projectSubtitle.textContent = `${project.project_code} · ${project.client_name} · ${project.location} · ${project.sector.replaceAll("_", " ")} · ${project.status}`;
  elements.projectNotes.textContent = project.notes || "No project notes captured yet.";
  elements.selectedProjectPermits.textContent = String(project.permits.length);
  elements.selectedProjectEvents.textContent = String(project.change_events.length);
  const pendingChangeOrders = project.change_events.flatMap((event) => event.change_orders).filter((item) => item.status === "pending_approval");
  elements.selectedProjectPending.textContent = String(pendingChangeOrders.length);
  const atRisk = project.change_events
    .filter((event) => ["draft", "pricing_requested", "priced", "internal_review", "owner_submitted"].includes(event.status))
    .reduce((total, event) => total + event.cost_impact_usd, 0);
  elements.selectedProjectCost.textContent = formatCurrency(atRisk);

  renderPermits();
  renderChangeEvents();
  renderWorkflow();
  applySessionState();
}

function renderPermits() {
  const project = state.selectedProject;
  if (!project || !project.permits.length) {
    elements.permitList.className = "site-list empty-state";
    elements.permitList.textContent = project
      ? "No permits yet. Add one manually or import a register CSV."
      : "Select a project to view permits.";
    return;
  }

  elements.permitList.className = "site-list";
  elements.permitList.innerHTML = project.permits
    .map((permit) => {
      const uploadId = `upload-${slug(permit.id)}`;
      return `
        <article class="site-result-card">
          <div class="site-result-header">
            <div>
              <strong>${permit.name}</strong>
              <p class="muted-text">${permit.jurisdiction} · ${permit.status} · inspection ${permit.inspection_status}</p>
            </div>
            <span class="pill">${permit.package_name || "General package"}</span>
          </div>
          <p class="muted-text">Permit #${permit.permit_number || "TBD"} · due ${permit.submission_due_date ? formatDate(permit.submission_due_date) : "Not set"} · blocker ${permit.current_blocker || "None"}</p>
          <p class="muted-text">${permit.notes || "No additional notes captured."}</p>
          <div class="project-actions">
            ${permit.linked_change_event_id ? `<button class="ghost small" type="button" data-open-change-event="${permit.linked_change_event_id}">Open linked event</button>` : ""}
            <button class="ghost small" type="button" data-update-permit="${permit.id}" data-status="revision_requested">Flag revision</button>
            <button class="ghost small" type="button" data-update-permit="${permit.id}" data-status="approved">Mark approved</button>
            <button class="ghost small" type="button" data-update-permit="${permit.id}" data-inspection="failed">Fail inspection</button>
          </div>
          <div class="file-row">
            <input id="${uploadId}" type="file" />
            <button class="ghost small" type="button" data-upload-permit="${permit.id}" data-input-id="${uploadId}">Upload document</button>
          </div>
        </article>
      `;
    })
    .join("");

  elements.permitList.querySelectorAll("[data-open-change-event]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedChangeEventId = button.dataset.openChangeEvent;
      state.selectedChangeOrderId = null;
      renderWorkflow();
      renderChangeEvents();
    });
  });

  elements.permitList.querySelectorAll("[data-update-permit]").forEach((button) => {
    button.addEventListener("click", async () => {
      const payload = {};
      if (button.dataset.status) {
        payload.status = button.dataset.status;
      }
      if (button.dataset.inspection) {
        payload.inspection_status = button.dataset.inspection;
      }
      try {
        await apiRequest(`/api/permits/${button.dataset.updatePermit}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        setStatus("Permit updated.", "success");
        await refreshWorkspace(state.selectedProject.id, state.selectedChangeEventId);
      } catch (error) {
        setStatus(error.message, "error");
      }
    });
  });

  elements.permitList.querySelectorAll("[data-upload-permit]").forEach((button) => {
    button.addEventListener("click", async () => {
      const fileInput = document.getElementById(button.dataset.inputId);
      const file = fileInput.files[0];
      if (!file) {
        setStatus("Choose a file before uploading.", "error");
        return;
      }
      const formData = new FormData();
      formData.append("file", file);
      try {
        await apiRequest(`/api/permits/${button.dataset.uploadPermit}/documents`, {
          method: "POST",
          body: formData,
        });
        fileInput.value = "";
        setStatus("Document uploaded and analyzed.", "success");
        await refreshWorkspace(state.selectedProject.id, state.selectedChangeEventId);
      } catch (error) {
        setStatus(error.message, "error");
      }
    });
  });
}

function renderChangeEvents() {
  const project = state.selectedProject;
  if (!project || !project.change_events.length) {
    elements.changeEventList.className = "site-list empty-state";
    elements.changeEventList.textContent = project
      ? "No change events yet. Permit blockers can create them automatically, or you can add one manually."
      : "Select a project to view change events.";
    return;
  }

  if (!project.change_events.find((event) => event.id === state.selectedChangeEventId)) {
    state.selectedChangeEventId = project.change_events[0].id;
  }

  elements.changeEventList.className = "site-list";
  elements.changeEventList.innerHTML = project.change_events
    .map((event) => {
      const selected = event.id === state.selectedChangeEventId;
      return `
        <article class="site-result-card ${selected ? "selected-card" : ""}">
          <div class="site-result-header">
            <div>
              <strong>${event.title}</strong>
              <p class="muted-text">${event.source_type.replaceAll("_", " ")} · ${event.status.replaceAll("_", " ")} · ${event.affected_scope || "Scope pending"}</p>
            </div>
            <button class="ghost small" type="button" data-select-change-event="${event.id}">${selected ? "Selected" : "Open"}</button>
          </div>
          <p class="muted-text">${event.summary || "No summary captured."}</p>
          <div class="result-chip-row">
            <span class="pill">${formatCurrency(event.cost_impact_usd)}</span>
            <span class="pill">${event.schedule_impact_days} day impact</span>
            ${(event.risk_tags || []).map((tag) => `<span class="pill subdued">${tag.replaceAll("_", " ")}</span>`).join("")}
          </div>
          <p class="muted-text">${event.rfqs.length} RFQs · ${event.quotes.length} quotes · ${event.change_orders.length} change orders</p>
        </article>
      `;
    })
    .join("");

  elements.changeEventList.querySelectorAll("[data-select-change-event]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedChangeEventId = button.dataset.selectChangeEvent;
      state.selectedChangeOrderId = null;
      renderChangeEvents();
      renderWorkflow();
    });
  });
}

async function loadOwnerPackagePreview(changeOrderId) {
  if (!changeOrderId) {
    elements.ownerPackagePreview.textContent = "Owner package preview will appear here.";
    return;
  }
  try {
    const payload = await apiRequest(`/api/change-orders/${changeOrderId}/package.md`);
    elements.ownerPackagePreview.textContent = payload.markdown;
  } catch (error) {
    elements.ownerPackagePreview.textContent = `Unable to load owner package.\n\n${error.message}`;
  }
}

function renderWorkflow() {
  const event = currentChangeEvent();
  if (!event) {
    elements.workflowTitle.textContent = "No change event selected";
    elements.workflowSummary.className = "empty-state";
    elements.workflowSummary.textContent = "Select a change event to create RFQs, quotes, and change orders.";
    elements.changeOrderList.className = "site-list empty-state";
    elements.changeOrderList.textContent = "Create or select a change event to see packaged change orders.";
    elements.ownerPackagePreview.textContent = "Owner package preview will appear here.";
    applySessionState();
    return;
  }

  if (!event.change_orders.find((item) => item.id === state.selectedChangeOrderId)) {
    state.selectedChangeOrderId = event.change_orders[0]?.id || null;
  }

  elements.workflowTitle.textContent = event.title;
  elements.workflowSummary.className = "stack";
  elements.workflowSummary.innerHTML = `
    <div class="workflow-card">
      <p class="muted-text">${event.summary || "No summary captured."}</p>
      <p class="muted-text">Scope: ${event.affected_scope || "Not set"} · Cost exposure: ${formatCurrency(event.cost_impact_usd)} · Schedule exposure: ${event.schedule_impact_days} days</p>
      <p class="muted-text">Required action: ${event.required_action_date ? formatDate(event.required_action_date) : "Not set"} · Subcontractor: ${event.subcontractor_name || "Unassigned"}</p>
    </div>
    <div class="results-grid compact-grid">
      <article class="workflow-card">
        <strong>RFQs</strong>
        <div class="mini-list">
          ${event.rfqs.length
            ? event.rfqs
                .map(
                  (rfq) => `<div class="mini-item">${rfq.subcontractor_name} · ${rfq.status} · due ${rfq.due_at ? formatDate(rfq.due_at) : "Not set"}</div>`
                )
                .join("")
            : '<div class="mini-item muted-text">No RFQs yet.</div>'}
        </div>
      </article>
      <article class="workflow-card">
        <strong>Quotes</strong>
        <div class="mini-list">
          ${event.quotes.length
            ? event.quotes
                .map(
                  (quote) => `<div class="mini-item">${quote.subcontractor_name} · ${formatCurrency(quote.amount_usd)}${quote.is_selected ? " · selected" : ""}</div>`
                )
                .join("")
            : '<div class="mini-item muted-text">No quotes yet.</div>'}
        </div>
      </article>
    </div>
  `;

  if (!event.change_orders.length) {
    elements.changeOrderList.className = "site-list empty-state";
    elements.changeOrderList.textContent = "No change orders yet. Create one from the selected event.";
    elements.ownerPackagePreview.textContent = "Owner package preview will appear here.";
    applySessionState();
    return;
  }

  const currentOrder = currentChangeOrder();
  elements.changeOrderList.className = "site-list";
  elements.changeOrderList.innerHTML = event.change_orders
    .map((order) => {
      const selected = currentOrder && currentOrder.id === order.id;
      const approvalButtons = order.approvals
        .map((step) => {
          const actions = step.status === "pending" && canActOnApproval(step)
            ? `
                <div class="project-actions">
                  <button class="ghost small" type="button" data-approval-step="${step.id}" data-approval-status="approved">Approve</button>
                  <button class="ghost danger small" type="button" data-approval-step="${step.id}" data-approval-status="rejected">Reject</button>
                </div>
              `
            : "";
          return `
            <div class="mini-item">
              Step ${step.step_order}: ${step.role_required.replaceAll("_", " ")} · ${step.status}
              ${actions}
            </div>
          `;
        })
        .join("");

      return `
        <article class="site-result-card ${selected ? "selected-card" : ""}">
          <div class="site-result-header">
            <div>
              <strong>${order.number}</strong>
              <p class="muted-text">${order.kind} · ${order.status.replaceAll("_", " ")} · ${formatCurrency(order.amount_usd)} · ${order.schedule_impact_days} days</p>
            </div>
            <div class="project-actions">
              <button class="ghost small" type="button" data-select-change-order="${order.id}">${selected ? "Selected" : "Open"}</button>
              ${["draft", "rejected"].includes(order.status) ? `<button class="primary small" type="button" data-submit-change-order="${order.id}">Submit</button>` : ""}
            </div>
          </div>
          <p class="muted-text">${order.description || "No description provided."}</p>
          <div class="mini-list">${approvalButtons || '<div class="mini-item muted-text">No approvals routed yet.</div>'}</div>
        </article>
      `;
    })
    .join("");

  elements.changeOrderList.querySelectorAll("[data-select-change-order]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedChangeOrderId = button.dataset.selectChangeOrder;
      renderWorkflow();
      await loadOwnerPackagePreview(state.selectedChangeOrderId);
    });
  });

  elements.changeOrderList.querySelectorAll("[data-submit-change-order]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await apiRequest(`/api/change-orders/${button.dataset.submitChangeOrder}/submit-approval`, {
          method: "POST",
        });
        state.selectedChangeOrderId = button.dataset.submitChangeOrder;
        setStatus("Change order submitted for approval.", "success");
        await refreshWorkspace(state.selectedProject.id, state.selectedChangeEventId);
      } catch (error) {
        setStatus(error.message, "error");
      }
    });
  });

  elements.changeOrderList.querySelectorAll("[data-approval-step]").forEach((button) => {
    button.addEventListener("click", async () => {
      const order = currentChangeOrder();
      if (!order) {
        return;
      }
      const notes = window.prompt(
        button.dataset.approvalStatus === "approved"
          ? "Optional approval note"
          : "Enter a rejection note"
      );
      if (notes === null) {
        return;
      }
      try {
        await apiRequest(
          `/api/change-orders/${order.id}/approval-steps/${button.dataset.approvalStep}/decision`,
          {
            method: "POST",
            body: JSON.stringify({
              status: button.dataset.approvalStatus,
              decision_notes: notes,
            }),
          }
        );
        setStatus("Approval step updated.", "success");
        await refreshWorkspace(state.selectedProject.id, state.selectedChangeEventId);
      } catch (error) {
        setStatus(error.message, "error");
      }
    });
  });

  applySessionState();
  loadOwnerPackagePreview(currentOrder.id);
}

function renderUsers() {
  if (!state.session.canManageUsers) {
    return;
  }
  if (!state.users.length) {
    elements.userList.className = "site-list empty-state";
    elements.userList.textContent = "No workspace users loaded yet.";
    return;
  }

  elements.userList.className = "site-list";
  elements.userList.innerHTML = state.users
    .map((user) => {
      return `
        <article class="site-result-card">
          <div class="site-result-header">
            <div>
              <strong>${user.full_name || user.username}</strong>
              <p class="muted-text">${user.username} · ${user.email} · ${user.role.replaceAll("_", " ")}</p>
            </div>
            <span class="pill">${user.is_active ? "Active" : "Inactive"}</span>
          </div>
          <p class="muted-text">Last login: ${user.last_login_at ? formatDateTime(user.last_login_at) : "Never"} · Locked until: ${user.locked_until ? formatDateTime(user.locked_until) : "Not locked"}</p>
          <div class="field-row">
            <label>
              Role
              <select data-user-role="${user.id}">
                <option value="project_engineer" ${user.role === "project_engineer" ? "selected" : ""}>Project engineer</option>
                <option value="project_manager" ${user.role === "project_manager" ? "selected" : ""}>Project manager</option>
                <option value="finance_approver" ${user.role === "finance_approver" ? "selected" : ""}>Finance approver</option>
                <option value="workspace_admin" ${user.role === "workspace_admin" ? "selected" : ""}>Workspace admin</option>
                <option value="viewer" ${user.role === "viewer" ? "selected" : ""}>Viewer</option>
              </select>
            </label>
            <label>
              Active
              <select data-user-active="${user.id}">
                <option value="true" ${user.is_active ? "selected" : ""}>Active</option>
                <option value="false" ${!user.is_active ? "selected" : ""}>Inactive</option>
              </select>
            </label>
          </div>
          <div class="project-actions">
            <button class="ghost small" type="button" data-user-save="${user.id}">Save access</button>
            <button class="ghost small" type="button" data-user-reset="${user.id}">Reset password</button>
          </div>
        </article>
      `;
    })
    .join("");

  elements.userList.querySelectorAll("[data-user-save]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = button.dataset.userSave;
      const role = elements.userList.querySelector(`[data-user-role="${userId}"]`).value;
      const isActive = elements.userList.querySelector(`[data-user-active="${userId}"]`).value === "true";
      try {
        await apiRequest(`/api/admin/users/${userId}`, {
          method: "PATCH",
          body: JSON.stringify({ role, is_active: isActive }),
        });
        setStatus("User access updated.", "success");
        await Promise.all([loadUsers(), loadActivity()]);
      } catch (error) {
        setStatus(error.message, "error");
      }
    });
  });

  elements.userList.querySelectorAll("[data-user-reset]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = button.dataset.userReset;
      const password = window.prompt("Enter a new password for this user.");
      if (!password) {
        return;
      }
      try {
        await apiRequest(`/api/admin/users/${userId}`, {
          method: "PATCH",
          body: JSON.stringify({ password }),
        });
        setStatus("Password reset.", "success");
        await Promise.all([loadUsers(), loadActivity()]);
      } catch (error) {
        setStatus(error.message, "error");
      }
    });
  });
}

function renderActivity() {
  if (!state.activity.length) {
    elements.activityList.className = "site-list empty-state";
    elements.activityList.textContent = "No recent activity recorded yet.";
    return;
  }

  elements.activityList.className = "site-list";
  elements.activityList.innerHTML = state.activity
    .map(
      (event) => `
        <article class="site-result-card">
          <div class="site-result-header">
            <div>
              <strong>${event.description}</strong>
              <p class="muted-text">${event.actor_username} · ${event.action}</p>
            </div>
            <span class="pill">${formatDateTime(event.created_at)}</span>
          </div>
          <p class="muted-text">${event.entity_type}${event.project_id ? ` · project ${event.project_id}` : ""}</p>
        </article>
      `
    )
    .join("");
}

async function loadSession() {
  const payload = await apiRequest("/api/session");
  state.session.authRequired = payload.auth_required;
  state.session.authenticated = payload.authenticated;
  state.session.canWrite = payload.permissions.can_write;
  state.session.canManageUsers = payload.permissions.can_manage_users;
  state.session.canApproveFinancials = payload.permissions.can_approve_financials;
  state.session.csrfToken = payload.csrf_token || "";
  state.session.username = payload.current_user?.username || "";
  state.session.role = payload.current_user?.role || "";
  state.workspace.name = payload.workspace?.name || pageDataset.workspaceName || "Open workspace";
}

async function loadDashboard() {
  state.dashboard = await apiRequest("/api/dashboard");
  renderDashboard();
}

async function loadProjectSummaries() {
  state.projects = await apiRequest("/api/projects");
  renderProjects();
}

async function loadProject(projectId) {
  state.selectedProject = await apiRequest(`/api/projects/${projectId}`);
  if (!state.selectedProject.change_events.find((event) => event.id === state.selectedChangeEventId)) {
    state.selectedChangeEventId = state.selectedProject.change_events[0]?.id || null;
  }
  const event = currentChangeEvent();
  if (!event || !event.change_orders.find((item) => item.id === state.selectedChangeOrderId)) {
    state.selectedChangeOrderId = event?.change_orders[0]?.id || null;
  }
  renderProjects();
  renderSelectedProject();
}

async function loadUsers() {
  if (!state.session.canManageUsers) {
    state.users = [];
    return;
  }
  state.users = await apiRequest("/api/admin/users");
  renderUsers();
}

async function loadActivity() {
  state.activity = await apiRequest("/api/activity");
  renderActivity();
}

async function refreshWorkspace(projectId = state.selectedProject?.id, changeEventId = state.selectedChangeEventId) {
  await Promise.all([loadSession(), loadDashboard(), loadProjectSummaries(), loadActivity(), loadUsers()]);
  if (!state.projects.length) {
    resetProjectDetails();
    applySessionState();
    return;
  }
  const nextProjectId = state.projects.find((project) => project.id === projectId)?.id || state.projects[0].id;
  state.selectedChangeEventId = changeEventId;
  await loadProject(nextProjectId);
}

function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

elements.projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(elements.projectForm);
  const payload = Object.fromEntries(formData.entries());
  payload.contract_value_usd = Number(payload.contract_value_usd || 0);
  payload.target_margin_pct = Number(payload.target_margin_pct || 0);
  if (!payload.start_date) {
    delete payload.start_date;
  }
  if (!payload.end_date) {
    delete payload.end_date;
  }

  try {
    const project = await apiRequest("/api/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.projectForm.reset();
    setStatus("Project created.", "success");
    await refreshWorkspace(project.id);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.permitForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedProject) {
    setStatus("Select a project first.", "error");
    return;
  }

  const formData = new FormData(elements.permitForm);
  const payload = Object.fromEntries(formData.entries());
  if (!payload.submission_due_date) {
    delete payload.submission_due_date;
  }
  if (!payload.inspection_due_date) {
    delete payload.inspection_due_date;
  }
  payload.dependencies = [];
  payload.inspections = [];

  try {
    await apiRequest(`/api/projects/${state.selectedProject.id}/permits`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.permitForm.reset();
    setStatus("Permit added.", "success");
    await refreshWorkspace(state.selectedProject.id, state.selectedChangeEventId);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.importPermitsButton.addEventListener("click", async () => {
  if (!state.selectedProject) {
    setStatus("Select a project first.", "error");
    return;
  }
  const file = elements.permitImportFile.files[0];
  if (!file) {
    setStatus("Choose a CSV file before importing.", "error");
    return;
  }
  try {
    const csvContent = await file.text();
    const result = await apiRequest("/api/permits/import", {
      method: "POST",
      body: JSON.stringify({
        project_id: state.selectedProject.id,
        csv_content: csvContent,
      }),
    });
    elements.permitImportFile.value = "";
    setStatus(`Imported ${result.created_count} permits.`, "success");
    await refreshWorkspace(state.selectedProject.id, state.selectedChangeEventId);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.changeEventForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedProject) {
    setStatus("Select a project first.", "error");
    return;
  }
  const formData = new FormData(elements.changeEventForm);
  const payload = Object.fromEntries(formData.entries());
  payload.cost_impact_usd = Number(payload.cost_impact_usd || 0);
  payload.schedule_impact_days = Number(payload.schedule_impact_days || 0);
  payload.risk_tags = [];
  if (!payload.required_action_date) {
    delete payload.required_action_date;
  }

  try {
    const changeEvent = await apiRequest(`/api/projects/${state.selectedProject.id}/change-events`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.changeEventForm.reset();
    state.selectedChangeEventId = changeEvent.id;
    state.selectedChangeOrderId = null;
    setStatus("Change event created.", "success");
    await refreshWorkspace(state.selectedProject.id, changeEvent.id);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.rfqForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedEvent = currentChangeEvent();
  if (!selectedEvent) {
    setStatus("Select a change event first.", "error");
    return;
  }
  const formData = new FormData(elements.rfqForm);
  const payload = Object.fromEntries(formData.entries());
  if (!payload.due_at) {
    delete payload.due_at;
  }
  if (!payload.sent_at) {
    delete payload.sent_at;
  }
  try {
    await apiRequest(`/api/change-events/${selectedEvent.id}/rfqs`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.rfqForm.reset();
    setStatus("RFQ created.", "success");
    await refreshWorkspace(state.selectedProject.id, selectedEvent.id);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.quoteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedEvent = currentChangeEvent();
  if (!selectedEvent) {
    setStatus("Select a change event first.", "error");
    return;
  }
  const formData = new FormData(elements.quoteForm);
  const payload = Object.fromEntries(formData.entries());
  payload.amount_usd = Number(payload.amount_usd || 0);
  payload.is_selected = elements.quoteForm.querySelector("[name='is_selected']").checked;
  if (!payload.quoted_at) {
    delete payload.quoted_at;
  }
  try {
    await apiRequest(`/api/change-events/${selectedEvent.id}/quotes`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.quoteForm.reset();
    setStatus("Quote recorded.", "success");
    await refreshWorkspace(state.selectedProject.id, selectedEvent.id);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.changeOrderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedEvent = currentChangeEvent();
  if (!selectedEvent) {
    setStatus("Select a change event first.", "error");
    return;
  }
  const formData = new FormData(elements.changeOrderForm);
  const payload = Object.fromEntries(formData.entries());
  payload.amount_usd = Number(payload.amount_usd || 0);
  payload.schedule_impact_days = Number(payload.schedule_impact_days || 0);
  try {
    const changeOrder = await apiRequest(`/api/change-events/${selectedEvent.id}/change-orders`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.changeOrderForm.reset();
    state.selectedChangeOrderId = changeOrder.id;
    setStatus("Change order created.", "success");
    await refreshWorkspace(state.selectedProject.id, selectedEvent.id);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.deleteProjectButton.addEventListener("click", async () => {
  if (!state.selectedProject) {
    return;
  }
  if (!window.confirm(`Delete project "${state.selectedProject.name}"?`)) {
    return;
  }
  try {
    await apiRequest(`/api/projects/${state.selectedProject.id}`, {
      method: "DELETE",
    });
    setStatus("Project deleted.", "success");
    await refreshWorkspace();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.exportProjectButton.addEventListener("click", async () => {
  if (!state.selectedProject) {
    return;
  }
  try {
    const payload = await apiRequest(`/api/projects/${state.selectedProject.id}/export`);
    downloadFile(
      `${slug(state.selectedProject.project_code || state.selectedProject.name)}-export.json`,
      JSON.stringify(payload, null, 2),
      "application/json"
    );
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.refreshWorkspaceButton.addEventListener("click", async () => {
  try {
    setStatus("Refreshing workspace...", "info");
    await refreshWorkspace();
    setStatus("Workspace refreshed.", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

if (elements.logoutButton) {
  elements.logoutButton.addEventListener("click", async () => {
    try {
      await apiRequest("/api/session/logout", { method: "POST" });
      window.location.assign("/login");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });
}

if (elements.userForm) {
  elements.userForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(elements.userForm);
    const payload = Object.fromEntries(formData.entries());
    try {
      await apiRequest("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      elements.userForm.reset();
      setStatus("Workspace user created.", "success");
      await Promise.all([loadUsers(), loadActivity()]);
    } catch (error) {
      setStatus(error.message, "error");
    }
  });
}

elements.submitSelectedApprovalButton.addEventListener("click", async () => {
  const order = currentChangeOrder();
  if (!order) {
    setStatus("Select a change order first.", "error");
    return;
  }
  try {
    await apiRequest(`/api/change-orders/${order.id}/submit-approval`, { method: "POST" });
    setStatus("Change order submitted for approval.", "success");
    await refreshWorkspace(state.selectedProject.id, state.selectedChangeEventId);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.downloadOwnerPackageButton.addEventListener("click", async () => {
  const order = currentChangeOrder();
  if (!order) {
    setStatus("Select a change order first.", "error");
    return;
  }
  try {
    const payload = await apiRequest(`/api/change-orders/${order.id}/package.md`);
    elements.ownerPackagePreview.textContent = payload.markdown;
    downloadFile(`${slug(order.number)}-owner-package.md`, payload.markdown, "text/markdown");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.downloadPermitTemplate.addEventListener("click", async () => {
  try {
    const template = await apiRequest("/api/reference/permit-template.csv");
    downloadFile("permit-intake-template.csv", template, "text/csv");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.downloadChangeEventTemplate.addEventListener("click", async () => {
  try {
    const template = await apiRequest("/api/reference/change-event-template.csv");
    downloadFile("change-event-template.csv", template, "text/csv");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

async function bootstrap() {
  try {
    setStatus("Loading workspace...", "info");
    await refreshWorkspace();
    setStatus("Workspace ready.", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

bootstrap();
