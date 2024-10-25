<template>
    <div class="container">
      <h1>尺码排序工具</h1>
      
      <div class="upload-box">
        <input
          type="file"
          @change="handleFileChange"
          accept=".xlsx,.xls,.csv"
        />
        
        <button 
          @click="processFile" 
          :disabled="!selectedFile"
          class="process-btn"
        >
          开始处理
        </button>
      </div>
  
      <!-- 结果显示 -->
      <div v-if="processedData.length" class="result-section">
        <div class="download-buttons">
          <button @click="downloadFile('excel')" class="download-btn">
            下载Excel
          </button>
          <button @click="downloadFile('csv')" class="download-btn">
            下载CSV
          </button>
        </div>
  
        <table>
          <thead>
            <tr>
              <th v-for="(header, index) in headers" :key="index">{{ header }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIndex) in displayData" :key="rowIndex">
              <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>
  
      <div v-if="errorMessage" class="error-message">
        {{ errorMessage }}
      </div>
    </div>
  </template>
  
  <script>
  import { ref, computed } from 'vue'
  import * as XLSX from 'xlsx'
  
  export default {
    setup() {
      const selectedFile = ref(null)
      const errorMessage = ref('')
      const processedData = ref([])
  
      const headers = computed(() => {
        return processedData.value.length > 0 ? processedData.value[0] : []
      })
  
      const displayData = computed(() => {
        return processedData.value.slice(1)
      })
  
      const handleFileChange = (event) => {
        const file = event.target.files[0]
        if (file) {
          if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls') || file.name.endsWith('.csv')) {
            selectedFile.value = file
            errorMessage.value = ''
          } else {
            errorMessage.value = '请上传 .xlsx, .xls 或 .csv 文件'
            event.target.value = ''
            selectedFile.value = null
          }
        }
      }
  
      const processFile = async () => {
        if (!selectedFile.value) {
          errorMessage.value = '请先选择文件'
          return
        }
  
        try {
          const reader = new FileReader()
          
          reader.onload = async (e) => {
            try {
              const data = new Uint8Array(e.target.result)
              const workbook = XLSX.read(data, { type: 'array' })
              const firstSheet = workbook.Sheets[workbook.SheetNames[0]]
              const jsonData = XLSX.utils.sheet_to_json(firstSheet, { header: 1 })
              
              console.log('发送到后端的数据:', jsonData)
  
              const response = await fetch('http://localhost:8000/process-data', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                  data: jsonData,
                  rows_per_column: 30
                })
              })
  
              if (!response.ok) {
                const errorData = await response.json()
                throw new Error(errorData.detail || '处理失败')
              }
  
              const result = await response.json()
              processedData.value = result.processed_data
  
            } catch (error) {
              console.error('错误详情:', error)
              errorMessage.value = '处理文件失败: ' + error.message
            }
          }
  
          reader.readAsArrayBuffer(selectedFile.value)
  
        } catch (error) {
          console.error('读取文件错误:', error)
          errorMessage.value = '读取文件失败'
        }
      }
  
      const downloadFile = async (format) => {
        try {
          const response = await fetch(`http://localhost:8000/download/${format}`, {
            method: 'GET',
          })
  
          if (!response.ok) {
            throw new Error('下载失败')
          }
  
          const blob = await response.blob()
          const url = window.URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `size_records.${format}`
          document.body.appendChild(a)
          a.click()
          window.URL.revokeObjectURL(url)
          a.remove()
  
        } catch (error) {
          errorMessage.value = '下载文件失败: ' + error.message
        }
      }
  
      return {
        selectedFile,
        errorMessage,
        processedData,
        headers,
        displayData,
        handleFileChange,
        processFile,
        downloadFile
      }
    }
  }
  </script>
  
  <style scoped>
  .container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
  }
  
  h1 {
    text-align: center;
    margin-bottom: 20px;
  }
  
  .upload-box {
    text-align: center;
    margin: 20px 0;
  }
  
  .process-btn {
    margin-left: 10px;
    padding: 8px 16px;
    background-color: #4CAF50;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  
  .process-btn:disabled {
    background-color: #cccccc;
    cursor: not-allowed;
  }
  
  .download-buttons {
    margin-bottom: 20px;
    text-align: right;
  }
  
  .download-btn {
    margin-left: 10px;
    padding: 8px 16px;
    background-color: #2196F3;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  
  .download-btn:hover {
    background-color: #1976D2;
  }
  
  table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 20px;
  }
  
  th, td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
  }
  
  th {
    background-color: #f5f5f5;
  }
  
  .error-message {
    color: red;
    text-align: center;
    margin-top: 10px;
  }
  </style>