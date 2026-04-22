const AUTH_TOKEN_KEY = "campus_admin_token_v1";

const fallbackSupplyGoals = {
  猫粮: 120,
  狗粮: 100,
  药品: 50,
  保暖用品: 80
};

const fallbackNotices = [
  "平台数据加载中，请稍候。",
  "请优先处理高紧急度救助工单。"
];

const rescueActionTextMap = {
  待处理: "接单并指派",
  已接单: "更新为送医中",
  送医中: "标记已完成"
};

let state = {
  pets: [],
  rescues: [],
  losts: [],
  events: [],
  donations: [],
  adoptionRequests: [],
  pendingAdoptionCount: 0,
  supplyGoals: fallbackSupplyGoals,
  notices: fallbackNotices,
  rescueFlow: ["待处理", "已接单", "送医中", "已完成"],
  viewer: {
    isAdmin: false,
    username: ""
  }
};

let noticeIndex = 0;
let noticeTimer = null;
let modalContext = null;

const refs = {
  statPets: document.getElementById("statPets"),
  statAdoptable: document.getElementById("statAdoptable"),
  statPendingAdoption: document.getElementById("statPendingAdoption"),
  statOpenRescue: document.getElementById("statOpenRescue"),
  statVolunteer: document.getElementById("statVolunteer"),
  supplyProgress: document.getElementById("supplyProgress"),
  noticeTicker: document.getElementById("noticeTicker"),
  petList: document.getElementById("petList"),
  rescueList: document.getElementById("rescueList"),
  lostList: document.getElementById("lostList"),
  donationList: document.getElementById("donationList"),
  adoptionList: document.getElementById("adoptionList"),
  eventList: document.getElementById("eventList"),
  toast: document.getElementById("toast"),
  petSearch: document.getElementById("petSearch"),
  speciesFilter: document.getElementById("speciesFilter"),
  statusFilter: document.getElementById("statusFilter"),
  rescueFilter: document.getElementById("rescueFilter"),
  lostFilter: document.getElementById("lostFilter"),
  petForm: document.getElementById("petForm"),
  rescueForm: document.getElementById("rescueForm"),
  lostForm: document.getElementById("lostForm"),
  donationForm: document.getElementById("donationForm"),
  adminAuthBtn: document.getElementById("adminAuthBtn"),
  adminStatusText: document.getElementById("adminStatusText"),
  modalBackdrop: document.getElementById("modalBackdrop"),
  modalTitle: document.getElementById("modalTitle"),
  modalForm: document.getElementById("modalForm")
};

function getToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

function setToken(token) {
  if (!token) {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    return;
  }
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

function showToast(message) {
  refs.toast.textContent = message;
  refs.toast.classList.add("show");
  window.setTimeout(() => refs.toast.classList.remove("show"), 2000);
}

function h(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTime(isoTime) {
  const d = new Date(isoTime);
  if (Number.isNaN(d.getTime())) {
    return String(isoTime ?? "");
  }
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function badgeClassByStatus(status) {
  if (status === "可领养" || status === "已完成" || status === "已找回" || status === "已通过" || status === "已领养") {
    return "green";
  }
  if (status === "高" || status === "走失" || status === "待处理" || status === "未解决" || status === "已拒绝") {
    return "red";
  }
  return "orange";
}

async function apiRequest(path, options = {}) {
  const request = { ...options };
  const token = getToken();
  request.headers = {
    ...(options.headers || {})
  };
  if (token) {
    request.headers.Authorization = `Bearer ${token}`;
  }
  if (request.body !== undefined) {
    request.headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, request);
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = {};
    }
  }

  if (!response.ok || payload.ok === false) {
    const error = new Error(payload.message || `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload.data ?? payload;
}

async function loadBootstrapData() {
  const data = await apiRequest("/api/bootstrap");
  state = {
    pets: Array.isArray(data.pets) ? data.pets : [],
    rescues: Array.isArray(data.rescues) ? data.rescues : [],
    losts: Array.isArray(data.losts) ? data.losts : [],
    events: Array.isArray(data.events) ? data.events : [],
    donations: Array.isArray(data.donations) ? data.donations : [],
    adoptionRequests: Array.isArray(data.adoptionRequests) ? data.adoptionRequests : [],
    pendingAdoptionCount: Number(data.pendingAdoptionCount || 0),
    supplyGoals: data.supplyGoals || fallbackSupplyGoals,
    notices: Array.isArray(data.notices) && data.notices.length ? data.notices : fallbackNotices,
    rescueFlow: Array.isArray(data.rescueFlow) && data.rescueFlow.length ? data.rescueFlow : state.rescueFlow,
    viewer: data.viewer || { isAdmin: false, username: "" }
  };
}

function renderAdminStatus() {
  if (state.viewer.isAdmin) {
    refs.adminAuthBtn.textContent = "管理员退出";
    refs.adminStatusText.textContent = `已登录：${state.viewer.username}`;
    return;
  }
  refs.adminAuthBtn.textContent = "管理员登录";
  refs.adminStatusText.textContent = "未登录";
}

function renderStats() {
  const petTotal = state.pets.length;
  const adoptableTotal = state.pets.filter((pet) => pet.status === "可领养").length;
  const pendingAdoptionTotal = state.pendingAdoptionCount;
  const openRescueTotal = state.rescues.filter((item) => item.status !== "已完成").length;
  const volunteerTotal = state.events.reduce((sum, item) => sum + (Number(item.participants) || 0), 0);

  refs.statPets.textContent = String(petTotal);
  refs.statAdoptable.textContent = String(adoptableTotal);
  refs.statPendingAdoption.textContent = String(pendingAdoptionTotal);
  refs.statOpenRescue.textContent = String(openRescueTotal);
  refs.statVolunteer.textContent = String(volunteerTotal);

  const grouped = groupDonationByCategory();
  refs.supplyProgress.innerHTML = Object.entries(state.supplyGoals)
    .map(([key, goal]) => {
      const amount = grouped[key] || 0;
      const percent = Math.min(100, Math.round((amount / goal) * 100));
      return `
        <div class="progress-item">
          <strong>${h(key)}：${amount}/${goal}</strong>
          <div class="bar"><span style="width:${percent}%"></span></div>
        </div>
      `;
    })
    .join("");
}

function groupDonationByCategory() {
  return state.donations.reduce((acc, item) => {
    const current = Number(item.amount) || 0;
    acc[item.category] = (acc[item.category] || 0) + current;
    return acc;
  }, {});
}

function renderPets() {
  const keyword = refs.petSearch.value.trim().toLowerCase();
  const species = refs.speciesFilter.value;
  const status = refs.statusFilter.value;

  const rows = state.pets
    .filter((item) => (species === "全部" ? true : item.species === species))
    .filter((item) => (status === "全部" ? true : item.status === status))
    .filter((item) => {
      if (!keyword) {
        return true;
      }
      return (
        String(item.name).toLowerCase().includes(keyword) ||
        String(item.health).toLowerCase().includes(keyword) ||
        String(item.personality).toLowerCase().includes(keyword)
      );
    });

  if (!rows.length) {
    refs.petList.innerHTML = `<article class="item-card"><p class="item-meta">暂无符合条件的宠物信息。</p></article>`;
    return;
  }

  refs.petList.innerHTML = rows
    .map((item) => {
      const canApply = item.status === "可领养";
      const inReview = item.status === "审核中";
      return `
      <article class="item-card">
        <div class="card-top">
          <h3>${h(item.name)} · ${h(item.species)}</h3>
          <span class="badge ${badgeClassByStatus(item.status)}">${h(item.status)}</span>
        </div>
        <p class="item-meta">年龄：${Number(item.age) || 0}个月 | 健康：${h(item.health)}</p>
        <p class="item-meta">性格：${h(item.personality)} | 登记：${h(formatTime(item.createdAt))}</p>
        <div class="card-actions">
          ${canApply ? `<button class="btn btn-success" data-action="adopt-apply" data-id="${h(item.id)}">提交领养申请</button>` : ""}
          ${inReview ? `<span class="badge orange">已有申请待审核</span>` : ""}
          <button class="btn btn-ghost" data-action="contact">联系负责人</button>
        </div>
      </article>
      `;
    })
    .join("");
}

function renderAdoptionRequests() {
  if (!state.viewer.isAdmin) {
    refs.adoptionList.innerHTML = `
      <article class="item-card">
        <p class="item-meta">领养申请审核仅管理员可见，请先登录管理员账号。</p>
        <div class="card-actions">
          <button class="btn btn-primary" data-action="open-admin-login">管理员登录</button>
        </div>
      </article>
    `;
    return;
  }

  const rows = [...state.adoptionRequests];
  if (!rows.length) {
    refs.adoptionList.innerHTML = `<article class="item-card"><p class="item-meta">暂无领养申请记录。</p></article>`;
    return;
  }

  refs.adoptionList.innerHTML = rows
    .map((item) => {
      const pending = item.status === "待审核";
      return `
      <article class="item-card">
        <div class="card-top">
          <h3>${h(item.petName)} · ${h(item.petSpecies)}</h3>
          <span class="badge ${badgeClassByStatus(item.status)}">${h(item.status)}</span>
        </div>
        <p class="item-meta">申请人：${h(item.applicantName)}（${h(item.applicantContact)}）</p>
        <p class="item-meta">居住条件：${h(item.housing)}</p>
        <p class="item-meta">养宠经验：${h(item.experience)}</p>
        <p class="item-meta">照护承诺：${h(item.commitment)}</p>
        <p class="item-meta">创建时间：${h(formatTime(item.createdAt))}</p>
        ${item.reviewedAt ? `<p class="item-meta">审核人：${h(item.reviewer || "管理员")} | 审核时间：${h(formatTime(item.reviewedAt))}</p>` : ""}
        ${item.remark ? `<p class="item-meta">审核备注：${h(item.remark)}</p>` : ""}
        <div class="card-actions">
          ${
            pending
              ? `<button class="btn btn-success" data-action="approve-adoption" data-id="${h(item.id)}">审核通过</button>
                 <button class="btn btn-danger" data-action="reject-adoption" data-id="${h(item.id)}">审核拒绝</button>`
              : ""
          }
        </div>
      </article>
      `;
    })
    .join("");
}

function renderRescues() {
  const rescueFilter = refs.rescueFilter.value;
  const rows = state.rescues.filter((item) => (rescueFilter === "全部" ? true : item.urgency === rescueFilter));

  if (!rows.length) {
    refs.rescueList.innerHTML = `<article class="item-card"><p class="item-meta">当前没有对应的救助工单。</p></article>`;
    return;
  }

  refs.rescueList.innerHTML = rows
    .map((item) => {
      const actionText = rescueActionTextMap[item.status] || "";
      const showAction = item.status !== "已完成" && state.viewer.isAdmin;
      return `
      <article class="item-card">
        <div class="card-top">
          <h3>${h(item.location)}</h3>
          <span class="badge ${badgeClassByStatus(item.urgency)}">紧急度 ${h(item.urgency)}</span>
        </div>
        <p class="item-meta">上报人：${h(item.reporter)} | 状态：${h(item.status)}</p>
        <p class="item-meta">处理人：${h(item.assignee || "未指派")}</p>
        <p class="item-meta">情况：${h(item.description)}</p>
        <p class="item-meta">创建：${h(formatTime(item.createdAt))}${item.updatedAt ? ` | 更新：${h(formatTime(item.updatedAt))}` : ""}</p>
        <div class="card-actions">
          ${showAction ? `<button class="btn btn-success" data-action="advance-rescue" data-id="${h(item.id)}" data-status="${h(item.status)}">${h(actionText)}</button>` : ""}
          ${!state.viewer.isAdmin && item.status !== "已完成" ? `<span class="badge orange">需管理员推进</span>` : ""}
        </div>
      </article>
      `;
    })
    .join("");
}

function renderLosts() {
  const lostFilter = refs.lostFilter.value;
  const rows = state.losts.filter((item) => (lostFilter === "全部" ? true : item.type === lostFilter));

  if (!rows.length) {
    refs.lostList.innerHTML = `<article class="item-card"><p class="item-meta">暂无走失或发现信息。</p></article>`;
    return;
  }

  refs.lostList.innerHTML = rows
    .map((item) => {
      return `
      <article class="item-card">
        <div class="card-top">
          <h3>${h(item.petName)}</h3>
          <span class="badge ${badgeClassByStatus(item.type)}">${h(item.type)}</span>
        </div>
        <p class="item-meta">区域：${h(item.area)}</p>
        <p class="item-meta">详情：${h(item.detail)}</p>
        <p class="item-meta">联系：${h(item.contact)} | 状态：${h(item.status)}</p>
        <div class="card-actions">
          ${item.status !== "已找回" ? `<button class="btn btn-success" data-action="resolve-lost" data-id="${h(item.id)}">标记已找回</button>` : ""}
        </div>
      </article>
      `;
    })
    .join("");
}

function renderEvents() {
  refs.eventList.innerHTML = state.events
    .map((item) => {
      return `
      <article class="event-card">
        <h3>${h(item.title)}</h3>
        <p>地点：${h(item.place)}</p>
        <p>时间：${h(item.time)}</p>
        <p>${h(item.desc)}</p>
        <p><strong>当前报名：${Number(item.participants) || 0} 人</strong></p>
        <button class="btn btn-primary" data-action="join-event" data-id="${h(item.id)}">我要报名</button>
      </article>
      `;
    })
    .join("");
}

function renderDonations() {
  const rows = [...state.donations].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  refs.donationList.innerHTML = rows
    .map((item) => {
      return `
      <article class="item-card">
        <div class="card-top">
          <h3>${h(item.category)} × ${Number(item.amount) || 0}</h3>
          <span class="badge orange">物资入库</span>
        </div>
        <p class="item-meta">捐助人：${h(item.donor)}</p>
        <p class="item-meta">备注：${h(item.note || "无")}</p>
        <p class="item-meta">登记时间：${h(formatTime(item.createdAt))}</p>
      </article>
      `;
    })
    .join("");
}

function renderNotice() {
  const notices = state.notices.length ? state.notices : fallbackNotices;
  refs.noticeTicker.textContent = notices[noticeIndex];
  noticeIndex = (noticeIndex + 1) % notices.length;
}

function renderAll() {
  renderAdminStatus();
  renderStats();
  renderPets();
  renderAdoptionRequests();
  renderRescues();
  renderLosts();
  renderEvents();
  renderDonations();
}

async function reloadAndRender(successMessage = "") {
  await loadBootstrapData();
  renderAll();
  if (successMessage) {
    showToast(successMessage);
  }
}

function closeModal() {
  modalContext = null;
  refs.modalForm.innerHTML = "";
  refs.modalBackdrop.classList.remove("show");
}

function fieldToHtml(field) {
  const type = field.type || "text";
  const required = field.required ? "required" : "";
  const value = field.value ? `value="${h(field.value)}"` : "";
  if (type === "textarea") {
    return `
      <label class="modal-label">${h(field.label)}
        <textarea name="${h(field.name)}" rows="${field.rows || 3}" placeholder="${h(field.placeholder || "")}" ${required}>${h(field.value || "")}</textarea>
      </label>
    `;
  }
  if (type === "select") {
    const options = (field.options || [])
      .map((opt) => {
        const selected = opt.value === field.value ? "selected" : "";
        return `<option value="${h(opt.value)}" ${selected}>${h(opt.label)}</option>`;
      })
      .join("");
    return `
      <label class="modal-label">${h(field.label)}
        <select name="${h(field.name)}" ${required}>${options}</select>
      </label>
    `;
  }
  if (type === "hidden") {
    return `<input type="hidden" name="${h(field.name)}" ${value}>`;
  }
  return `
    <label class="modal-label">${h(field.label)}
      <input type="${h(type)}" name="${h(field.name)}" placeholder="${h(field.placeholder || "")}" ${required} ${value}>
    </label>
  `;
}

function openModal(config) {
  modalContext = config;
  refs.modalTitle.textContent = config.title || "表单";
  const descriptionHtml = config.description ? `<p class="modal-desc">${h(config.description)}</p>` : "";
  const fieldsHtml = (config.fields || []).map((field) => fieldToHtml(field)).join("");
  refs.modalForm.innerHTML = `
    ${descriptionHtml}
    ${fieldsHtml}
    <div class="modal-actions">
      <button type="button" class="btn btn-ghost" data-modal-close>${h(config.cancelText || "取消")}</button>
      <button type="submit" class="btn ${h(config.submitClass || "btn-primary")}">${h(config.submitText || "提交")}</button>
    </div>
  `;
  refs.modalBackdrop.classList.add("show");
}

function openAdminLoginModal() {
  openModal({
    title: "管理员登录",
    description: "登录后可执行领养审核与救助流程推进。",
    fields: [
      { name: "username", label: "管理员账号", required: true, placeholder: "请输入管理员账号" },
      { name: "password", label: "管理员密码", type: "password", required: true, placeholder: "请输入密码" }
    ],
    submitText: "登录",
    async onSubmit(values) {
      const data = await apiRequest("/api/admin/login", {
        method: "POST",
        body: JSON.stringify({
          username: String(values.username || "").trim(),
          password: String(values.password || "").trim()
        })
      });
      setToken(data.token);
      await reloadAndRender("管理员登录成功");
    }
  });
}

function openAdminLogoutModal() {
  openModal({
    title: "退出管理员登录",
    description: "退出后将无法执行审核和工单推进操作。",
    fields: [],
    submitText: "确认退出",
    submitClass: "btn-danger",
    async onSubmit() {
      await apiRequest("/api/admin/logout", { method: "POST" });
      clearToken();
      await reloadAndRender("已退出管理员登录");
    }
  });
}

function openAdoptionApplyModal(petId) {
  openModal({
    title: "提交领养申请",
    description: "请完整填写信息，提交后进入管理员审核。",
    fields: [
      { name: "applicantName", label: "申请人姓名", required: true, placeholder: "请输入姓名" },
      { name: "applicantContact", label: "联系方式", required: true, placeholder: "手机号/微信" },
      { name: "housing", label: "居住条件", required: true, placeholder: "如：校内宿舍/校外自住房" },
      { name: "experience", label: "养宠经验", type: "textarea", placeholder: "可填写既往养宠经历" },
      { name: "commitment", label: "照护承诺", type: "textarea", placeholder: "可填写回访与照护承诺" }
    ],
    submitText: "提交申请",
    async onSubmit(values) {
      await apiRequest(`/api/pets/${petId}/adoption-requests`, {
        method: "POST",
        body: JSON.stringify({
          applicantName: String(values.applicantName || "").trim(),
          applicantContact: String(values.applicantContact || "").trim(),
          housing: String(values.housing || "").trim(),
          experience: String(values.experience || "").trim(),
          commitment: String(values.commitment || "").trim()
        })
      });
      await reloadAndRender("领养申请已提交，等待审核");
    }
  });
}

function openReviewModal(requestId, decision) {
  openModal({
    title: decision === "通过" ? "审核通过" : "审核拒绝",
    description: "请填写审核信息并确认提交。",
    fields: [
      { name: "reviewer", label: "审核人", required: true, value: state.viewer.username || "管理员" },
      { name: "remark", label: "审核备注", type: "textarea", placeholder: decision === "通过" ? "可填写补充说明" : "请填写拒绝原因" }
    ],
    submitText: "确认提交",
    submitClass: decision === "通过" ? "btn-success" : "btn-danger",
    async onSubmit(values) {
      await apiRequest(`/api/adoption-requests/${requestId}/review`, {
        method: "PATCH",
        body: JSON.stringify({
          decision,
          reviewer: String(values.reviewer || "").trim(),
          remark: String(values.remark || "").trim()
        })
      });
      await reloadAndRender(decision === "通过" ? "领养申请已通过" : "领养申请已拒绝");
    }
  });
}

function openRescueAdvanceModal(rescueId, currentStatus) {
  const needAssignee = currentStatus === "待处理";
  openModal({
    title: "推进救助工单",
    description: needAssignee ? "首次接单必须填写处理人。" : "可选更新处理人信息。",
    fields: [
      {
        name: "assignee",
        label: "处理人",
        required: needAssignee,
        placeholder: "请输入处理人姓名"
      }
    ],
    submitText: "确认推进",
    async onSubmit(values) {
      await apiRequest(`/api/rescues/${rescueId}/advance`, {
        method: "PATCH",
        body: JSON.stringify({
          assignee: String(values.assignee || "").trim()
        })
      });
      await reloadAndRender("救助工单状态已推进");
    }
  });
}

function openEventSignupModal(eventId) {
  openModal({
    title: "活动报名",
    description: "请填写报名信息（同一联系方式不可重复报名同一活动）。",
    fields: [
      { name: "name", label: "报名人姓名", required: true, placeholder: "请输入姓名" },
      { name: "contact", label: "联系方式", required: true, placeholder: "手机号/微信" }
    ],
    submitText: "确认报名",
    async onSubmit(values) {
      await apiRequest(`/api/events/${eventId}/join`, {
        method: "POST",
        body: JSON.stringify({
          name: String(values.name || "").trim(),
          contact: String(values.contact || "").trim()
        })
      });
      await reloadAndRender("报名成功，感谢你的参与");
    }
  });
}

function handleApiError(error, defaultMsg) {
  if (error && error.status === 401) {
    clearToken();
    showToast("请先进行管理员登录");
    openAdminLoginModal();
    return;
  }
  showToast((error && error.message) || defaultMsg);
}

refs.modalBackdrop.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  if (target === refs.modalBackdrop || target.dataset.modalClose !== undefined) {
    closeModal();
  }
});

refs.modalForm.addEventListener("click", (event) => {
  const target = event.target;
  if (target instanceof HTMLElement && target.dataset.modalClose !== undefined) {
    closeModal();
  }
});

refs.modalForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!modalContext) {
    return;
  }
  const values = Object.fromEntries(new FormData(refs.modalForm).entries());
  try {
    await modalContext.onSubmit(values);
    closeModal();
  } catch (error) {
    handleApiError(error, "提交失败");
  }
});

refs.adminAuthBtn.addEventListener("click", () => {
  if (state.viewer.isAdmin) {
    openAdminLogoutModal();
    return;
  }
  openAdminLoginModal();
});

refs.petForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }
  const formData = new FormData(form);
  try {
    await apiRequest("/api/pets", {
      method: "POST",
      body: JSON.stringify({
        name: String(formData.get("name")).trim(),
        species: String(formData.get("species")).trim(),
        age: Number(formData.get("age")) || 1,
        health: String(formData.get("health")).trim(),
        personality: String(formData.get("personality")).trim(),
        status: String(formData.get("status")).trim()
      })
    });
    form.reset();
    await reloadAndRender("宠物档案已新增");
  } catch (error) {
    handleApiError(error, "保存失败");
  }
});

refs.rescueForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }
  const formData = new FormData(form);
  try {
    await apiRequest("/api/rescues", {
      method: "POST",
      body: JSON.stringify({
        reporter: String(formData.get("reporter")).trim(),
        location: String(formData.get("location")).trim(),
        description: String(formData.get("description")).trim(),
        urgency: String(formData.get("urgency")).trim()
      })
    });
    form.reset();
    await reloadAndRender("救助工单已提交");
  } catch (error) {
    handleApiError(error, "提交失败");
  }
});

refs.lostForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }
  const formData = new FormData(form);
  try {
    await apiRequest("/api/losts", {
      method: "POST",
      body: JSON.stringify({
        type: String(formData.get("type")).trim(),
        petName: String(formData.get("petName")).trim(),
        area: String(formData.get("area")).trim(),
        detail: String(formData.get("detail")).trim(),
        contact: String(formData.get("contact")).trim()
      })
    });
    form.reset();
    await reloadAndRender("寻宠信息已发布");
  } catch (error) {
    handleApiError(error, "发布失败");
  }
});

refs.donationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }
  const formData = new FormData(form);
  try {
    await apiRequest("/api/donations", {
      method: "POST",
      body: JSON.stringify({
        donor: String(formData.get("donor")).trim(),
        category: String(formData.get("category")).trim(),
        amount: Number(formData.get("amount")) || 1,
        note: String(formData.get("note")).trim()
      })
    });
    form.reset();
    await reloadAndRender("捐助记录已入库");
  } catch (error) {
    handleApiError(error, "提交失败");
  }
});

refs.petSearch.addEventListener("input", renderPets);
refs.speciesFilter.addEventListener("change", renderPets);
refs.statusFilter.addEventListener("change", renderPets);
refs.rescueFilter.addEventListener("change", renderRescues);
refs.lostFilter.addEventListener("change", renderLosts);

document.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const action = target.dataset.action;
  if (!action) {
    return;
  }
  const id = target.dataset.id;

  if (action === "contact") {
    showToast("已通知对应负责人进行回访");
    return;
  }
  if (action === "open-admin-login") {
    openAdminLoginModal();
    return;
  }

  try {
    if (action === "adopt-apply" && id) {
      openAdoptionApplyModal(id);
      return;
    }
    if (action === "approve-adoption" && id) {
      if (!state.viewer.isAdmin) {
        openAdminLoginModal();
        return;
      }
      openReviewModal(id, "通过");
      return;
    }
    if (action === "reject-adoption" && id) {
      if (!state.viewer.isAdmin) {
        openAdminLoginModal();
        return;
      }
      openReviewModal(id, "拒绝");
      return;
    }
    if (action === "advance-rescue" && id) {
      if (!state.viewer.isAdmin) {
        openAdminLoginModal();
        return;
      }
      openRescueAdvanceModal(id, target.dataset.status || "");
      return;
    }
    if (action === "resolve-lost" && id) {
      await apiRequest(`/api/losts/${id}/resolve`, { method: "PATCH" });
      await reloadAndRender("已更新为“已找回”");
      return;
    }
    if (action === "join-event" && id) {
      openEventSignupModal(id);
    }
  } catch (error) {
    handleApiError(error, "操作失败");
  }
});

function initNoticeTimer() {
  renderNotice();
  if (noticeTimer !== null) {
    clearInterval(noticeTimer);
  }
  noticeTimer = window.setInterval(renderNotice, 4200);
}

async function bootstrap() {
  try {
    await loadBootstrapData();
    renderAll();
    initNoticeTimer();
    showToast("已启用弹窗表单与管理员权限");
  } catch (error) {
    clearToken();
    showToast((error && error.message) || "数据初始化失败，请检查服务是否启动");
  }
}

bootstrap();
