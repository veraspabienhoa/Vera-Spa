import { Component, Fragment } from 'react'

export default class PageErrorBoundary extends Component {
  state = { failed: false, attempt: 0 }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  retry = () => {
    this.props.onRetry?.()
    this.setState(({ attempt }) => ({ failed: false, attempt: attempt + 1 }))
  }

  render() {
    if (!this.state.failed) return <Fragment key={this.state.attempt}>{this.props.children}</Fragment>
    const url = new URL(window.location.href)
    url.searchParams.set('standalone', '1')
    url.searchParams.set('page', this.props.page)
    url.searchParams.set('reload', String(Date.now()))
    return <section className="panel page-recovery" role="alert" aria-labelledby="page-recovery-title">
      <h2 id="page-recovery-title">Không mở được {this.props.page === 'leave' ? 'Đăng ký nghỉ' : 'chức năng này'}</h2>
      <p>Giao diện gặp lỗi khi tải hoặc hiển thị. Bạn có thể thử mở lại, hoặc mở bản mới trong tab khác.</p>
      <div className="page-recovery-actions">
        <button type="button" className="primary-button" onClick={this.retry}>Thử mở lại</button>
        <a className="secondary-button" href={url.href} target="_blank" rel="noopener noreferrer">Mở bản mới trong tab khác</a>
      </div>
    </section>
  }
}
