import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001'

export const api = axios.create({
  baseURL: `${API_BASE}/api`,
  timeout: 10000,
})

export const fetchAPI = async (endpoint) => {
  const response = await api.get(endpoint)
  return response.data
}

export const postAPI = async (endpoint, data) => {
  const response = await api.post(endpoint, data)
  return response.data
}
