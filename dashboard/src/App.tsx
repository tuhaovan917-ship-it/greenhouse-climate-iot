import { OverviewPage } from './features/overview/OverviewPage'
import {
  mockDeviceState,
  mockTelemetry,
  mockTelemetryHistoryByBucket,
} from './mocks/greenhouse'

export default function App() {
  return (
    <OverviewPage
      telemetry={mockTelemetry}
      deviceState={mockDeviceState}
      history={mockTelemetryHistoryByBucket}
      dataSource="mock"
    />
  )
}
