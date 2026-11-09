<template>
  <div class="mib-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="title">
            <span>{{ t('mib.mibManagement') }}</span>
            <el-tag size="small" type="info" effect="plain">{{ t('mib.importedCount', { count: mibs.length }) }}</el-tag>
          </div>
          <div class="actions">
            <el-button type="primary" size="small" :loading="uploading" :disabled="!canEdit" @click="openImportDialog">
              <el-icon><UploadFilled /></el-icon>{{ t('mib.importMibFile') }}
            </el-button>
            <el-button size="small" :loading="importingStandard" :disabled="!canEdit" @click="importStandard">
              <el-icon><Collection /></el-icon>{{ t('mib.importStandardLib') }}
            </el-button>
            <el-button size="small" :loading="importingBuiltin" :disabled="!canEdit" @click="importBuiltin">
              <el-icon><Files /></el-icon>{{ t('mib.importBuiltin') }}
            </el-button>
            <el-button size="small" type="success" plain :disabled="!canEdit" @click="openAutoMatch">
              <el-icon><MagicStick /></el-icon>设备自动匹配
            </el-button>
            <el-button size="small" @click="openOidTest()">
              <el-icon><Cpu /></el-icon>{{ t('mib.testOid') }}
            </el-button>
            <el-button size="small" @click="vendorLibraryVisible = true">
              <el-icon><Collection /></el-icon>厂商库
            </el-button>
            <el-button size="small" @click="loadMibs" :loading="loading">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="tip"
        :title="t('mib.mibTooltip')"
      />
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="tip"
        :title="t('mib.builtinTip')"
      />
      <el-alert
        v-if="hasMissingDeps"
        type="warning"
        :closable="false"
        show-icon
        class="tip"
        :title="t('mib.missingDepsTip')"
      />

      <div class="category-filter">
        <el-radio-group v-model="categoryFilter" size="small">
          <el-radio-button value="">{{ t('mib.categoryAll') }} {{ mibs.length }}</el-radio-button>
          <el-radio-button value="switch">{{ t('mib.categorySwitch') }} {{ categoryCount('switch') }}</el-radio-button>
          <el-radio-button value="server">{{ t('mib.categoryServer') }} {{ categoryCount('server') }}</el-radio-button>
          <el-radio-button value="storage">{{ t('mib.categoryStorage') }} {{ categoryCount('storage') }}</el-radio-button>
          <el-radio-button value="custom">{{ t('mib.categoryCustom') }} {{ categoryCount('custom') }}</el-radio-button>
        </el-radio-group>
        <el-select v-model="vendorFilter" clearable :placeholder="t('mib.vendor')" size="small" style="width: 125px">
          <el-option v-for="vendor in vendorOptions" :key="vendor" :label="vendor" :value="vendor" />
        </el-select>
        <el-select v-model="modelFilter" clearable placeholder="设备型号" size="small" style="width: 160px">
          <el-option v-for="model in modelOptions" :key="model" :label="model" :value="model" />
        </el-select>
        <el-input
          v-model="keywordFilter"
          clearable
          size="small"
          :placeholder="t('mib.searchMibPlaceholder')"
          style="width: 230px"
        />
      </div>

      <div v-if="canEdit && selectedMibs.length" class="mib-batch-toolbar">
        <span class="muted">已选择 {{ selectedMibs.length }} 个 MIB</span>
        <el-button size="small" type="primary" plain @click="openBatchAssign">批量引用到资产</el-button>
        <el-button size="small" type="primary" plain @click="openBatchClassify">批量归类</el-button>
        <el-button size="small" type="danger" plain @click="batchDeleteMibs">批量删除</el-button>
      </div>

      <el-table
        ref="mibTableRef"
        :data="pagedMibs"
        row-key="id"
        v-loading="loading"
        stripe
        @selection-change="onMibSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column prop="module_name" :label="t('mib.mibModule')" :min-width="isCompact ? 190 : 230">
          <template #default="{ row }">
            <div class="module-cell">
              <el-icon><Document /></el-icon>
              <div class="module-main">
                <div class="module-line">
                  <span>{{ row.module_name }}</span>
                  <el-tag v-if="row.is_builtin" size="small" type="success" effect="plain">
                    {{ t('mib.builtin') }}
                  </el-tag>
                </div>
                <div class="module-meta">
                  {{ row.vendor || '未标注厂商' }}<template v-if="row.device_model"> / {{ row.device_model }}</template>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="showMibExtras" prop="vendor" :label="t('mib.vendor')" width="95">
          <template #default="{ row }">{{ row.vendor || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="showMibExtras" prop="device_model" label="设备型号" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_model || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="showMibExtras" :label="t('mib.deviceCategory')" width="95">
          <template #default="{ row }">
            <el-tag v-if="row.device_category" size="small" effect="plain" :type="deviceCategoryType(row.device_category)">
              {{ deviceCategoryLabel(row.device_category) }}
            </el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isCompact" prop="filename" :label="t('mib.fileName')" min-width="220" show-overflow-tooltip />
        <el-table-column :label="t('mib.objectCount')" :width="isCompact ? 100 : 130">
          <template #default="{ row }">
            {{ row.object_count }}
            <span class="muted">{{ t('mib.readableCount', { count: row.readable_count }) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="showMibExtras" :label="t('mib.recognizedMetrics')" min-width="220">
          <template #default="{ row }">
            <el-tag
              v-for="cat in row.categories"
              :key="cat"
              size="small"
              class="tag-gap"
              :type="catType(cat)"
            >
              {{ categoryLabel(cat) }}
            </el-tag>
            <span v-if="!row.categories?.length" class="muted">{{ t('mib.unrecognized') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('mib.unresolved')" width="80">
          <template #default="{ row }">
            <span :class="row.unresolved_count > 0 ? 'warn' : 'muted'">
              {{ row.unresolved_count }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="showMibExtras" :label="t('mib.dependencies')" width="130">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.note"
              :content="row.note"
              placement="top"
              :show-after="300"
            >
              <el-tag v-if="row.note.includes('缺少依赖')" type="warning" size="small">
                {{ t('mib.depsMissing') }}
              </el-tag>
              <el-tag v-else-if="row.imports?.length" type="success" size="small">
                {{ t('mib.depsOk', { count: row.imports.length }) }}
              </el-tag>
              <span v-else class="muted">{{ t('mib.noDeps') }}</span>
            </el-tooltip>
            <span v-else-if="row.imports?.length" class="muted">
              {{ t('mib.depsOk', { count: row.imports.length }) }}
            </span>
            <span v-else class="muted">{{ t('mib.noDeps') }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="showMibExtras" :label="t('mib.size')" width="100">
          <template #default="{ row }">
            {{ row.is_builtin ? t('mib.builtin') : `${(row.size / 1024).toFixed(1)} KB` }}
          </template>
        </el-table-column>
        <el-table-column v-if="showMibExtras" :label="t('mib.importTime')" width="165">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('mib.actions')" :width="isCompact ? 190 : 220" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openDetail(row)">
              {{ t('mib.viewObjects') }}
            </el-button>
            <el-button type="primary" link size="small" @click="openRecommend(row)">
              {{ t('mib.recommendedOid') }}
            </el-button>
            <el-button type="danger" link size="small" :disabled="!canEdit" @click="removeMib(row)">
              {{ t('mib.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && filteredMibs.length === 0" :description="t('mib.noMibHint')" />

      <div class="mib-pager">
        <span class="muted">共 {{ filteredMibs.length }} 个 MIB</span>
        <el-pagination
          v-model:current-page="mibPage"
          v-model:page-size="mibPageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="filteredMibs.length"
          layout="sizes, prev, pager, next"
          background
          small
          @current-change="onMibPageChange"
          @size-change="onMibPageSizeChange"
        />
      </div>
    </el-card>

    <!-- 导入 MIB 文件：必须携带厂商 + 设备型号 -->
    <el-dialog
      v-model="importVisible"
      title="导入 MIB 文件"
      width="640px"
      :close-on-click-modal="false"
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="tip"
        title="同一厂商不同设备型号的 MIB 可能不同。本次选择的多个文件会统一登记为下方填写的厂商与设备型号。"
      />
      <el-form
        ref="importFormRef"
        :model="importForm"
        :rules="importRules"
        label-width="90px"
        @submit.prevent
      >
        <el-form-item label="厂商" prop="vendor">
          <el-select
            v-model="importForm.vendor"
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="选择或输入厂商，如 华为 / H3C"
            style="width: 100%"
          >
            <el-option v-for="vendor in importVendorOptions" :key="vendor" :label="vendor" :value="vendor" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备型号" prop="device_model">
          <el-input
            v-model="importForm.device_model"
            maxlength="120"
            show-word-limit
            clearable
            placeholder="如 S5735-L48T4X-A1 / PowerEdge R740"
          />
        </el-form-item>
        <el-form-item label="MIB 文件" required>
          <el-upload
            v-model:file-list="importFileList"
            :auto-upload="false"
            :multiple="true"
            :limit="10"
            accept=".mib,.my,.txt,.smidb,.asn1"
            :on-exceed="onImportExceed"
            drag
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">将文件拖到此处，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">每批最多 10 个文件，单个不超过 5MB；支持 .mib / .my / .txt / .smidb / .asn1</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitImport">导入</el-button>
      </template>
    </el-dialog>

    <!-- 对象浏览 -->
    <el-dialog v-model="detailVisible" :title="t('mib.objectDialogTitle', { name: current?.module_name || '' })" width="1100px" top="6vh">
      <div class="filters">
        <el-select v-model="objFilter.category" :placeholder="t('mib.allCategories')" clearable style="width: 150px" @change="loadObjects(1)">
          <el-option
            v-for="(label, key) in CATEGORY_LABELS"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
        <el-input
          v-model="objFilter.keyword"
          :placeholder="t('mib.searchObjectPlaceholder')"
          clearable
          style="width: 280px"
          @keyup.enter="loadObjects(1)"
          @clear="loadObjects(1)"
        />
        <el-button @click="loadObjects(1)">{{ t('mib.query') }}</el-button>
        <span class="muted">{{ t('mib.objectTotal', { count: objTotal }) }}</span>
      </div>

      <el-table :data="objects" v-loading="objLoading" size="small" max-height="520">
        <el-table-column prop="name" :label="t('mib.objectName')" width="230" show-overflow-tooltip />
        <el-table-column prop="oid" label="OID" width="230">
          <template #default="{ row }">
            <span class="oid-text">{{ row.oid }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="syntax" :label="t('mib.type')" width="150" show-overflow-tooltip />
        <el-table-column prop="access" :label="t('mib.access')" width="110" />
        <el-table-column :label="t('mib.category')" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.category" size="small" :type="catType(row.category)">
              {{ categoryLabel(row.category) }}
            </el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" :label="t('mib.description')" min-width="220" show-overflow-tooltip />
        <el-table-column :label="t('mib.actions')" width="90" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openOidTest(row)">
              {{ t('mib.test') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="objPage"
        :page-size="objSize"
        :total="objTotal"
        layout="total, prev, pager, next"
        class="pager"
        @current-change="loadObjects"
      />
    </el-dialog>

    <!-- 推荐 OID -->
    <el-dialog v-model="recommendVisible" :title="t('mib.recommendDialogTitle', { name: current?.module_name || '' })" width="900px">
      <el-alert
        type="success"
        :closable="false"
        show-icon
        class="tip"
        :title="t('mib.recommendTooltip')"
      />
      <el-row :gutter="14">
        <el-col v-for="(label, key) in CATEGORY_LABELS" :key="key" :span="12" class="rec-col">
          <div class="rec-card">
            <div class="rec-title">
              <span>{{ label }}</span>
              <el-tag v-if="autoMap[key]" type="success" size="small">{{ t('mib.recommendTag', { name: autoMap[key].name }) }}</el-tag>
            </div>
            <div v-if="recommendations[key]?.length" class="rec-list">
              <div
                v-for="item in recommendations[key]"
                :key="item.oid"
                class="rec-item"
                :class="{ active: autoMap[key]?.oid === item.oid }"
              >
                <div class="rec-name">
                  {{ item.name }}
                  <el-tag v-if="autoMap[key]?.oid === item.oid" size="small" type="success" effect="dark">{{ t('mib.auto') }}</el-tag>
                </div>
                <div class="rec-oid">{{ item.oid }}</div>
                <div class="rec-desc">{{ item.description || item.syntax }}</div>
              </div>
            </div>
            <div v-else class="muted">{{ t('mib.noMetricsForCategory') }}</div>
          </div>
        </el-col>
      </el-row>
      <template #footer>
        <el-button @click="recommendVisible = false">{{ t('mib.close') }}</el-button>
      </template>
    </el-dialog>

    <!-- OID 测试 -->
    <el-dialog v-model="autoMatchVisible" title="设备 MIB 自动识别与取值验证" width="min(1180px, 97vw)" top="3vh">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="tip"
        title="自动读取设备 SNMP 指纹，匹配已导入 MIB，并对推荐 OID 做真实取值校验；只有通过范围校验的指标才会自动归类。AI 仅辅助解释，不直接修改设备。"
      />
      <div class="auto-match-toolbar">
        <el-select v-model="autoDeviceId" filterable placeholder="选择要识别的设备" style="width: 330px" :loading="autoDeviceLoading">
          <el-option v-for="device in deviceOptions" :key="device.id" :label="deviceOptionLabel(device)" :value="device.id" />
        </el-select>
        <el-button type="primary" :loading="autoMatching" @click="runAutoMatch">开始识别并验证</el-button>
        <el-checkbox v-model="autoOnline" size="small">本地无候选时联网获取厂商 MIB</el-checkbox>
        <el-checkbox v-model="autoAi" size="small" :disabled="!aiConfigured" :title="aiConfigured ? '使用外部模型对候选 MIB 排序和解释' : '请先在 AI 智能运维中配置外部模型'">AI 辅助匹配</el-checkbox>
        <span v-if="!aiConfigured" class="auto-ai-muted">未配置外部模型</span>
        <span v-if="autoResult?.learned_profile?.success_count" class="auto-learned">
          已学习 {{ autoResult.learned_profile.success_count }} 次，同类设备会优先匹配
        </span>
      </div>
      <el-alert
        v-if="autoResult?.online"
        class="auto-online-alert"
        :type="autoResult.online.imported?.length ? 'success' : 'warning'"
        :closable="false"
        show-icon
        :title="autoResult.online.imported?.length ? `已联网获取并导入 ${autoResult.online.imported.length} 个 MIB（${autoResult.online.source || '在线库'}），已重新匹配` : `联网获取 MIB 未成功：${autoResult.online.errors?.[0] || '未找到可用 MIB'}`"
      />
      <el-alert
        v-if="autoResult?.ai?.recommended_mib_id"
        class="auto-online-alert"
        type="success"
        :closable="false"
        show-icon
        :title="`AI 推荐：${autoResult.ai.mib_name}（置信度 ${autoResult.ai.confidence}%）`"
        :description="autoResult.ai.reason || 'AI 仅做候选排序，实际绑定仍需通过 OID 校验'"
      />
      <el-alert
        v-else-if="autoResult?.ai?.error"
        class="auto-online-alert"
        type="warning"
        :closable="false"
        show-icon
        :title="autoResult.ai.error"
      />
      <div v-if="autoResult" class="auto-match-result">
        <div class="auto-device-fingerprint">
          <b>{{ autoResult.device?.name }}</b>
          <span>{{ autoResult.device?.ip_address }} · {{ autoResult.device?.vendor || '未识别厂商' }} / {{ autoResult.device?.model || '未识别型号' }}</span>
          <el-tag :type="autoResult.snmp?.reachable ? 'success' : 'warning'" size="small" effect="plain">
            {{ autoResult.snmp?.reachable ? 'SNMP 指纹已读取' : 'SNMP 指纹未读取' }}
          </el-tag>
          <small v-if="autoResult.snmp?.sys_descr">{{ autoResult.snmp.sys_descr }}</small>
          <small v-if="autoResult.snmp?.error" class="auto-error">{{ autoResult.snmp.error }}</small>
        </div>
        <el-empty v-if="!autoResult.candidates?.length" :description="autoResult.message || '没有匹配到已导入 MIB'" :image-size="60" />
        <div v-else class="auto-candidate-list">
          <div v-for="candidate in autoResult.candidates" :key="candidate.mib_id" class="auto-candidate" :class="{ best: candidate.mib_id === autoResult.best?.mib_id }">
            <div class="auto-candidate-head">
              <div>
                <strong>{{ candidate.module_name || candidate.filename }}</strong>
                <el-tag v-if="candidate.learned" type="success" size="small" effect="plain">历史学习</el-tag>
                <el-tag v-if="candidate.ai_recommended" type="success" size="small" effect="plain">AI推荐</el-tag>
                <el-tag v-if="candidate.mib_id === autoResult.best?.mib_id" type="warning" size="small" effect="plain">最佳候选</el-tag>
              </div>
              <div class="auto-score">
                <span>匹配度 <b>{{ candidate.confidence }}%</b></span>
                <span>有效 {{ candidate.valid_count }}/{{ candidate.tested_count }}</span>
                <el-button size="small" type="primary" :disabled="!candidate.valid_count" :loading="autoApplying" @click="applyAutoCandidate(candidate)">应用并归类</el-button>
              </div>
            </div>
            <div class="auto-candidate-meta">
              <span>{{ candidate.vendor || '未标注厂商' }} / {{ candidate.device_model || '通用' }}</span>
              <span>{{ candidate.device_category || '未分类' }}</span>
              <span v-if="candidate.categories?.length">指标：{{ candidate.categories.join('、') }}</span>
              <span>{{ candidate.recommendation }}</span>
            </div>
            <el-table :data="candidate.metrics" size="small" border max-height="260">
              <el-table-column label="归类" width="92">
                <template #default="{ row }"><el-tag size="small" :type="row.valid ? 'success' : 'info'" effect="plain">{{ CATEGORY_LABELS[row.category] || row.category }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="name" label="MIB 对象" min-width="180" show-overflow-tooltip />
              <el-table-column prop="oid" label="OID" min-width="220" show-overflow-tooltip />
              <el-table-column prop="value" label="实测值" width="130" show-overflow-tooltip />
              <el-table-column label="校验" width="90">
                <template #default="{ row }"><el-tag size="small" :type="row.valid ? 'success' : 'danger'" effect="plain">{{ row.valid ? '通过' : '不通过' }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="reason" label="校验说明" min-width="180" show-overflow-tooltip />
            </el-table>
          </div>
        </div>
      </div>
      <template #footer><el-button @click="autoMatchVisible = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog v-model="oidDialog" :title="t('mib.testOidTitle')" width="640px">
      <el-form label-width="90px">
        <el-form-item :label="t('mib.device')">
          <el-select
            v-model="oidTest.device_id"
            filterable
            clearable
            :placeholder="t('mib.selectDevice')"
            style="width: 100%"
          >
            <el-option
              v-for="d in deviceOptions"
              :key="d.id"
              :label="deviceOptionLabel(d)"
              :value="d.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="OID">
          <el-input v-model="oidTest.oid" placeholder="1.3.6.1.2.1.25.3.3.1.2.1" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="oidTesting" @click="runOidTest">
            <el-icon><Cpu /></el-icon>{{ t('mib.runTest') }}
          </el-button>
          <span class="muted" style="margin-left: 10px">{{ t('mib.testOidTip') }}</span>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="oidResult"
        :type="oidResult.ok ? 'success' : 'error'"
        :closable="false"
        show-icon
      >
        <template #title>
          <span v-if="oidResult.ok">
            {{ t('mib.testOk', {
              value: oidResult.value,
              numeric: oidResult.numeric ?? '-',
              ms: oidResult.elapsed_ms,
            }) }}
          </span>
          <span v-else>{{ oidResult.error || t('mib.testFailed') }}</span>
        </template>
      </el-alert>

      <template #footer>
        <el-button @click="oidDialog = false">{{ t('mib.close') }}</el-button>
      </template>
    </el-dialog>

    <!-- 批量引用 MIB 到资产设备 -->
    <el-dialog v-model="batchBindVisible" title="批量引用 MIB 到资产设备" width="700px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="引用会把所选设备原有的 MIB 关联替换为当前目标 MIB；不会删除设备已有的自定义 OID 指标。"
        class="tip"
      />
      <el-form label-width="110px">
        <el-form-item label="目标 MIB">
          <el-select v-model="batchMibId" filterable style="width: 100%">
            <el-option
              v-for="item in selectedMibs"
              :key="item.id"
              :label="mibOptionLabel(item)"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="资产设备">
          <el-select
            v-model="batchDeviceIds"
            multiple
            filterable
            collapse-tags
            clearable
            placeholder="选择要引用该 MIB 的设备，可多选"
            style="width: 100%"
          >
            <el-option
              v-for="device in deviceOptions"
              :key="device.id"
              :label="deviceOptionLabel(device)"
              :value="device.id"
            />
          </el-select>
          <div class="form-tip">共 {{ deviceOptions.length }} 台可见设备，选择项已显示目标设备所属厂商；引用会覆盖设备原 MIB 关联，并自动套用匹配的 CPU/内存/温度/风扇/电源采集 OID。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchBindVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="batchBinding"
          :disabled="!batchMibId || !batchDeviceIds.length"
          @click="submitBatchAssign"
        >
          确认引用
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchClassifyVisible" title="批量归类 MIB" width="600px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="只填写需要修改的字段；留空表示保持原值。"
        class="batch-classify-tip"
      />
      <el-form label-width="90px">
        <el-form-item label="厂商">
          <el-input v-model="batchClassify.vendor" placeholder="留空不修改，例如 Huawei" />
        </el-form-item>
        <el-form-item label="设备型号">
          <el-input v-model="batchClassify.device_model" placeholder="留空不修改，例如 S5735" />
        </el-form-item>
        <el-form-item label="设备分类">
          <el-select v-model="batchClassify.device_category" clearable placeholder="留空不修改" style="width: 100%">
            <el-option label="交换机" value="switch" />
            <el-option label="服务器" value="server" />
            <el-option label="存储" value="storage" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="batchClassify.note" type="textarea" :rows="2" placeholder="留空不修改" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchClassifyVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchClassifying" @click="submitBatchClassify">应用</el-button>
      </template>
    </el-dialog>

    <VendorLibraryDialog
      v-model="vendorLibraryVisible"
      :can-edit="canEdit"
      @changed="loadMibs"
    />
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { mibApi, assetApi, aiApi } from '@/api'
import { can } from '@/store/auth'
import { formatDateTime } from '@/utils/time'
import { useResponsiveViewport } from '@/composables/useResponsiveViewport'
import { VENDOR_OPTIONS } from '@/constants/device'
import VendorLibraryDialog from '@/components/VendorLibraryDialog.vue'

const { viewportWidth, isCompact } = useResponsiveViewport()
const showMibExtras = computed(() => viewportWidth.value >= 2100)

const CATEGORY_LABELS = {
  get cpu() { return t('mib.cpuUsage') },
  get memory() { return t('mib.memoryUsage') },
  get storage() { return t('mib.storageCapacity') },
  get temperature() { return t('mib.temperature') },
  get power() { return t('mib.powerStatus') },
  get optical() { return t('mib.opticalPower') },
  get fan() { return t('mib.fanSpeed') },
  get interface() { return t('mib.interfaces') },
}

const DEVICE_CATEGORY_LABELS = {
  get switch() { return t('mib.categorySwitch') },
  get server() { return t('mib.categoryServer') },
  get storage() { return t('mib.categoryStorage') },
}

const mibs = ref([])
const mibPage = ref(1)
const mibPageSize = ref(20)
const loading = ref(false)
const uploading = ref(false)
const canEdit = computed(() => can('mib:edit'))
const importingStandard = ref(false)
const importingBuiltin = ref(false)
const categoryFilter = ref('')
const vendorFilter = ref('')
const modelFilter = ref('')
const keywordFilter = ref('')
const selectedMibs = ref([])
const mibTableRef = ref(null)
const vendorLibraryVisible = ref(false)
const batchClassifyVisible = ref(false)
const batchClassifying = ref(false)
const batchClassify = reactive({ vendor: '', device_model: '', device_category: '', note: '' })
const batchBindVisible = ref(false)
const batchMibId = ref(null)
const batchDeviceIds = ref([])
const batchBinding = ref(false)

// 导入 MIB：厂商 + 设备型号为必填，本批文件共用
const importVisible = ref(false)
const importFormRef = ref(null)
const importForm = reactive({ vendor: '', device_model: '' })
const importFileList = ref([])
const importRules = {
  vendor: [{ required: true, message: '请填写厂商', trigger: 'change' }],
  device_model: [{ required: true, message: '请填写设备型号', trigger: 'blur' }],
}

const importVendorOptions = computed(() => {
  const merged = new Set(VENDOR_OPTIONS)
  mibs.value.forEach((item) => {
    if (item.vendor) merged.add(item.vendor)
  })
  return [...merged].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
})

const vendorOptions = computed(() => (
  [...new Set(mibs.value.map((item) => item.vendor).filter(Boolean))].sort()
))

const modelOptions = computed(() => {
  const source = vendorFilter.value
    ? mibs.value.filter((item) => item.vendor === vendorFilter.value)
    : mibs.value
  return [...new Set(source.map((item) => item.device_model).filter(Boolean))].sort()
})

watch(vendorFilter, () => {
  if (modelFilter.value && !modelOptions.value.includes(modelFilter.value)) {
    modelFilter.value = ''
  }
})

const filteredMibs = computed(() => {
  const keyword = keywordFilter.value.trim().toLowerCase()
  return mibs.value.filter((m) => {
    if (categoryFilter.value === 'custom' && m.is_builtin) return false
    if (categoryFilter.value && categoryFilter.value !== 'custom'
      && m.device_category !== categoryFilter.value) return false
    if (vendorFilter.value && m.vendor !== vendorFilter.value) return false
    if (modelFilter.value && m.device_model !== modelFilter.value) return false
    if (keyword) {
      const text = `${m.module_name || ''} ${m.filename || ''} ${m.vendor || ''} ${m.device_model || ''}`.toLowerCase()
      if (!text.includes(keyword)) return false
    }
    return true
  })
})

const pagedMibs = computed(() => {
  const start = (mibPage.value - 1) * mibPageSize.value
  return filteredMibs.value.slice(start, start + mibPageSize.value)
})

function onMibPageChange() {
  selectedMibs.value = []
  mibTableRef.value?.clearSelection()
}

function onMibPageSizeChange() {
  mibPage.value = 1
  onMibPageChange()
}

watch([categoryFilter, vendorFilter, modelFilter, keywordFilter], () => {
  mibPage.value = 1
  onMibPageChange()
})

function categoryCount(key) {
  if (key === 'custom') return mibs.value.filter((m) => !m.is_builtin).length
  return mibs.value.filter((m) => m.device_category === key).length
}

function onMibSelectionChange(rows) {
  selectedMibs.value = rows || []
}

async function batchDeleteMibs() {
  if (!selectedMibs.value.length) return
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${selectedMibs.value.length} 个 MIB？已引用这些 MIB 的设备会自动解除引用，设备自定义 OID 保留。`,
      '批量删除 MIB',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const res = await mibApi.batchDelete(selectedMibs.value.map((item) => item.id))
    ElMessage.success(res.data.message || `已删除 ${res.data.deleted} 个 MIB`)
    selectedMibs.value = []
    mibTableRef.value?.clearSelection()
    await loadMibs()
  } catch (e) {
    ElMessage.error(e.message || '批量删除 MIB 失败')
  }
}

function openBatchClassify() {
  if (!selectedMibs.value.length) return
  Object.assign(batchClassify, { vendor: '', device_model: '', device_category: '', note: '' })
  batchClassifyVisible.value = true
}

async function submitBatchClassify() {
  if (!selectedMibs.value.length) return
  const payload = { ids: selectedMibs.value.map((item) => item.id) }
  if (batchClassify.vendor.trim()) payload.vendor = batchClassify.vendor.trim()
  if (batchClassify.device_model.trim()) payload.device_model = batchClassify.device_model.trim()
  if (batchClassify.device_category) payload.device_category = batchClassify.device_category
  if (batchClassify.note.trim()) payload.note = batchClassify.note.trim()
  if (Object.keys(payload).length === 1) {
    ElMessage.warning('请至少填写一个要修改的字段')
    return
  }
  batchClassifying.value = true
  try {
    const res = await mibApi.batchUpdate(payload)
    ElMessage.success(res.data.message || `已更新 ${res.data.updated} 个 MIB`)
    batchClassifyVisible.value = false
    selectedMibs.value = []
    mibTableRef.value?.clearSelection()
    await loadMibs()
  } catch (e) {
    ElMessage.error(e.message || '批量归类 MIB 失败')
  } finally {
    batchClassifying.value = false
  }
}

async function openBatchAssign() {
  if (!selectedMibs.value.length) return
  batchMibId.value = selectedMibs.value[0].id
  batchDeviceIds.value = []
  batchBindVisible.value = true
  await loadDevices()
}

async function submitBatchAssign() {
  if (!batchMibId.value || !batchDeviceIds.value.length) return
  batchBinding.value = true
  try {
    const res = await mibApi.assignDevices(batchMibId.value, batchDeviceIds.value)
    ElMessage.success(res.data.message || `已引用到 ${res.data.assigned} 台设备`)
    batchBindVisible.value = false
    batchDeviceIds.value = []
    selectedMibs.value = []
    mibTableRef.value?.clearSelection()
  } catch (e) {
    ElMessage.error(e.message || '批量引用 MIB 失败')
  } finally {
    batchBinding.value = false
  }
}

const hasMissingDeps = computed(() =>
  mibs.value.some((m) => (m.note || '').includes('缺少依赖'))
)

// OID 测试
const oidDialog = ref(false)
const oidTesting = ref(false)
const oidResult = ref(null)
const oidTest = reactive({ device_id: null, oid: '' })

// 设备 MIB 自动匹配
const autoMatchVisible = ref(false)
const autoMatching = ref(false)
const autoOnline = ref(false)
const autoAi = ref(false)
const aiConfigured = ref(false)
const autoApplying = ref(false)
const autoDeviceLoading = ref(false)
const autoDeviceId = ref(null)
const autoResult = ref(null)
const deviceOptions = ref([])

const detailVisible = ref(false)
const recommendVisible = ref(false)
const current = ref(null)
const recommendations = ref({})
const autoMap = ref({})

const objects = ref([])
const objTotal = ref(0)
const objPage = ref(1)
const objSize = ref(50)
const objLoading = ref(false)
const objFilter = reactive({ category: '', keyword: '' })

const categoryLabel = (key) => CATEGORY_LABELS[key] || key
const deviceCategoryLabel = (key) => DEVICE_CATEGORY_LABELS[key] || key
const deviceCategoryType = (key) => ({ switch: 'primary', server: 'success', storage: 'warning' }[key] || 'info')
const catType = (key) => ({
  cpu: 'danger', memory: 'warning', storage: 'warning', temperature: 'success',
  power: 'info', optical: 'warning', fan: 'info', interface: 'primary',
}[key] || 'info')

async function loadMibs() {
  loading.value = true
  try {
    const res = await mibApi.list()
    mibs.value = res.data.items
    const maxPage = Math.max(1, Math.ceil(filteredMibs.value.length / mibPageSize.value))
    if (mibPage.value > maxPage) mibPage.value = maxPage
  } catch (e) {
    ElMessage.error(e.message || t('mib.loadMibListFailed'))
  } finally {
    loading.value = false
  }
}

function openImportDialog() {
  if (!canEdit.value) return
  importForm.vendor = ''
  importForm.device_model = ''
  importFileList.value = []
  importVisible.value = true
  nextTick(() => importFormRef.value?.clearValidate())
}

function onImportExceed() {
  ElMessage.warning('一次最多导入 10 个 MIB 文件')
}

async function submitImport() {
  if (!importFormRef.value) return
  try {
    await importFormRef.value.validate()
  } catch {
    return
  }
  const vendor = (importForm.vendor || '').trim()
  const deviceModel = (importForm.device_model || '').trim()
  if (!vendor) {
    ElMessage.warning('请填写厂商')
    return
  }
  if (!deviceModel) {
    ElMessage.warning('请填写设备型号')
    return
  }
  const files = (importFileList.value || []).map((item) => item.raw).filter(Boolean)
  if (!files.length) {
    ElMessage.warning('请选择 MIB 文件')
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('vendor', vendor)
    formData.append('device_model', deviceModel)
    files.forEach((file) => formData.append('files', file))
    const res = await mibApi.upload(formData)
    const imported = res.data.imported || []
    const errors = res.data.errors || []
    if (!imported.length) {
      const first = errors[0]
      ElMessage.error(first ? `导入失败：${first.filename}：${first.error}` : t('mib.importFailed'))
      return
    }
    ElMessage.success(`已导入 ${imported.length} 个 MIB（厂商：${vendor}，型号：${deviceModel}）`)
    const missing = [...new Set(imported.flatMap((item) => item.missing_imports || []))]
    if (missing.length) {
      ElMessage.warning(`缺少依赖：${missing.join('，')}`)
    }
    if (errors.length) {
      ElMessage.warning(`有 ${errors.length} 个文件失败：${errors[0].filename}：${errors[0].error}`)
    }
    importVisible.value = false
    importFileList.value = []
    await loadMibs()
  } catch (e) {
    ElMessage.error(e.message || t('mib.mibImportFailed'))
  } finally {
    uploading.value = false
  }
}

function mibOptionLabel(item) {
  const meta = [item.vendor, item.device_model].filter(Boolean).join(' / ')
  return `${item.module_name}${meta ? `（${meta}）` : '（未标注厂商/型号）'}`
}

async function openDetail(row) {
  current.value = row
  detailVisible.value = true
  objFilter.category = ''
  objFilter.keyword = ''
  await loadObjects(1)
}

async function loadObjects(page = 1) {
  objLoading.value = true
  try {
    const params = { page, size: objSize.value }
    if (objFilter.category) params.category = objFilter.category
    if (objFilter.keyword) params.keyword = objFilter.keyword
    const res = await mibApi.objects(current.value.id, params)
    objects.value = res.data.items
    objTotal.value = res.data.total
    objPage.value = page
  } catch (e) {
    ElMessage.error(e.message || t('mib.loadMibObjectsFailed'))
  } finally {
    objLoading.value = false
  }
}

async function openRecommend(row) {
  current.value = row
  recommendVisible.value = true
  try {
    const res = await mibApi.recommendations(row.id)
    recommendations.value = res.data.recommendations
    autoMap.value = res.data.auto_map || {}
  } catch (e) {
    ElMessage.error(e.message || t('mib.recommendFailed'))
  }
}

async function removeMib(row) {
  try {
    await ElMessageBox.confirm(
      t('mib.confirmDeleteMib', { name: row.module_name }),
      t('mib.confirmDelete'),
      { type: 'warning' }
    )
    const res = await mibApi.remove(row.id)
    ElMessage.success(t('mib.deletedUnbound', { count: res.data.devices_unbound }))
    await loadMibs()
  } catch {
    /* 取消 */
  }
}

async function importStandard() {
  importingStandard.value = true
  try {
    const res = await mibApi.importStandard()
    ElMessage.success(res.data.message || t('mib.importStandardSuccess'))
    await loadMibs()
  } catch (e) {
    ElMessage.error(e.message || t('mib.importStandardFailed'))
  } finally {
    importingStandard.value = false
  }
}

async function importBuiltin() {
  importingBuiltin.value = true
  try {
    const res = await mibApi.importBuiltin()
    ElMessage.success(res.data.message || t('mib.builtinImportSuccess'))
    await loadMibs()
  } catch (e) {
    ElMessage.error(e.message || t('mib.importFailed'))
  } finally {
    importingBuiltin.value = false
  }
}

async function loadDevices() {
  if (deviceOptions.value.length) return
  try {
    const all = []
    for (let page = 1; page <= 10; page += 1) {
      const res = await assetApi.getList({ page, size: 100 })
      const items = res.data.items || []
      all.push(...items)
      if (all.length >= Number(res.data.total || 0) || items.length < 100) break
    }
    deviceOptions.value = all
  } catch {
    /* 忽略 */
  }
}

function deviceOptionLabel(device) {
  return `${device.name}（${device.ip_address}）· ${device.vendor || '未标注厂商'}`
}

function openOidTest(row) {
  oidResult.value = null
  oidTest.oid = row?.oid || ''
  oidDialog.value = true
  loadDevices()
}

async function runOidTest() {
  if (!oidTest.oid.trim()) {
    ElMessage.warning(t('mib.enterOid'))
    return
  }
  if (!oidTest.device_id) {
    ElMessage.warning(t('mib.selectDevice'))
    return
  }
  oidTesting.value = true
  oidResult.value = null
  try {
    const res = await assetApi.testOid({
      device_id: oidTest.device_id,
      oid: oidTest.oid.trim(),
    })
    oidResult.value = res.data
  } catch (e) {
    oidResult.value = { ok: false, error: e.message || t('mib.testFailed') }
  } finally {
    oidTesting.value = false
  }
}

async function loadAiCapability() {
  try {
    const res = await aiApi.status()
    aiConfigured.value = Boolean(res.data?.configured)
  } catch {
    aiConfigured.value = false
  }
  if (!aiConfigured.value) autoAi.value = false
}

async function openAutoMatch() {
  autoMatchVisible.value = true
  autoResult.value = null
  loadAiCapability()
  if (!deviceOptions.value.length) {
    autoDeviceLoading.value = true
    try { await loadDevices() } finally { autoDeviceLoading.value = false }
  }
  if (!autoDeviceId.value && deviceOptions.value.length) {
    autoDeviceId.value = deviceOptions.value[0].id
  }
}

async function runAutoMatch() {
  if (!autoDeviceId.value) {
    ElMessage.warning('请选择设备')
    return
  }
  autoMatching.value = true
  autoResult.value = null
  try {
    const res = await mibApi.autoMatch({ device_id: autoDeviceId.value, apply: false, online: autoOnline.value, ai: autoAi.value })
    autoResult.value = res.data
    if (res.data?.snmp?.error) ElMessage.warning(`SNMP 探测提示：${res.data.snmp.error}`)
  } catch (e) {
    ElMessage.error(e.message || 'MIB 自动识别失败')
  } finally {
    autoMatching.value = false
  }
}

async function applyAutoCandidate(candidate) {
  if (!candidate?.valid_count) return
  autoApplying.value = true
  try {
    const res = await mibApi.autoBind({
      device_id: autoDeviceId.value,
      mib_id: candidate.mib_id,
      metrics: candidate.metrics || [],
      fingerprint: autoResult.value?.fingerprint || '',
    })
    ElMessage.success(res.data?.message || 'MIB 已匹配并完成指标归类')
    autoMatchVisible.value = false
    await loadMibs()
  } catch (e) {
    ElMessage.error(e.message || '应用 MIB 失败')
  } finally {
    autoApplying.value = false
  }
}

onMounted(loadMibs)
</script>

<style scoped>
.mib-view {
  height: 100%;
}

.mib-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
}

.batch-classify-tip {
  margin-bottom: 14px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 8px;
}

.tip {
  margin-bottom: 12px;
}

.category-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.mib-batch-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
  font-size: 12px;
}

.form-tip {
  margin-top: 5px;
  color: #8b9bab;
  font-size: 11px;
}

.module-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  min-width: 0;
}

.module-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.module-line {
  display: flex;
  align-items: center;
  gap: 6px;
}

.module-meta {
  color: #8b9bab;
  font-size: 11px;
  font-weight: 400;
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.muted {
  color: #a8abb2;
  font-size: 12px;
}

.warn {
  color: #e6a23c;
  font-weight: 600;
}

.tag-gap {
  margin-right: 4px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.pager {
  margin-top: 14px;
  justify-content: flex-end;
}

.rec-col {
  margin-bottom: 14px;
}

.rec-card {
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 12px;
  height: 100%;
  background: #fafcff;
}

.rec-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  margin-bottom: 8px;
}

.rec-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rec-item {
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #f0f2f5;
}

.rec-item.active {
  border-color: #67c23a;
  background: #f0f9eb;
}

.rec-name {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}

.rec-oid {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #409eff;
}

.rec-desc {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.oid-text {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #606266;
}


.auto-online-alert { margin: 8px 0; }
.auto-ai-muted { color: #9aa9b8; font-size: 10px; }
.auto-match-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 0;
}
.auto-learned {
  color: #0f766e;
  font-size: 11px;
}
.auto-match-result {
  margin-top: 8px;
}
.auto-device-fingerprint {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  margin-bottom: 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
  color: #334e63;
  font-size: 12px;
}
.auto-device-fingerprint > span { color: #70879a; }
.auto-device-fingerprint > small {
  flex-basis: 100%;
  color: #8b9bab;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.auto-device-fingerprint > small.auto-error { color: #d97706; }
.auto-candidate-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 62vh;
  overflow: auto;
}
.auto-candidate {
  border: 1px solid #e2eaf2;
  border-radius: 9px;
  overflow: hidden;
}
.auto-candidate.best {
  border-color: #67c7bb;
  box-shadow: 0 0 0 2px rgba(15, 118, 110, .08);
}
.auto-candidate-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: #fbfdff;
}
.auto-candidate-head > div:first-child {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.auto-candidate-head strong { color: #1e3a4f; font-size: 13px; }
.auto-score {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #70879a;
  font-size: 11px;
  white-space: nowrap;
}
.auto-score b { color: #0f766e; font-size: 14px; }
.auto-candidate-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 0 12px 9px;
  color: #8b9bab;
  font-size: 10px;
}
.auto-candidate :deep(.el-table) { border-left: 0; border-right: 0; }

</style>
