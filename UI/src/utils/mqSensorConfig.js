import mqSensorConfig from '../config/mqSensorConfig.json'

export const MQ_SAFE_RANGES = Object.fromEntries(
  Object.entries(mqSensorConfig.safeRanges).map(([sensorId, range]) => [Number(sensorId), range])
)

export const MQ_HIGH_THRESHOLD_OFFSET = Number(mqSensorConfig.highThresholdOffset)

export function classifyMqReading(sensorId, value) {
  const range = MQ_SAFE_RANGES[sensorId]
  if (!range || value == null) return null
  if (value > range.max + MQ_HIGH_THRESHOLD_OFFSET) return 'high'
  if (value > range.max) return 'elevated'
  return 'low'
}