import { Component, Fragment } from 'react'
import { hasNewPageBuild, isPageLoadFailure } from '../lib/pageLoadFailure'

export default class PageErrorBoundary extends Component {
  state = { failed: false, attempt: 0, loadFailure: false, newBuild: false }
  mounted = true

  componentWillUnmount() { this.mounted = false }

  componentDidCatch(error) {
    const attempt = this.state.attempt
    if (isPageLoadFailure(error)) void hasNewPageBuild().then(newBuild => {
      if (this.mounted && this.state.failed && this.state.attempt === attempt) this.setState({ newBuild })
    })
  }

  static getDerivedStateFromError(error) {
    return { failed: true, loadFailure: isPageLoadFailure(error), newBuild: false }
  }

  retry = () => {
    this.props.onRetry?.()
    this.setState(({ attempt }) => ({ failed: false, attempt: attempt + 1 }))
  }

  update = () => {
    const url = new URL(window.location.href)
    url.searchParams.set('standalone', '1')
    url.searchParams.set('page', this.props.page)
    url.searchParams.set('reload', String(Date.now()))
    window.location.assign(url.href)
  }

  render() {
    if (!this.state.failed) return <Fragment key={this.state.attempt}>{this.props.children}</Fragment>
    const url = new URL(window.location.href)
    url.searchParams.set('standalone', '1')
    url.searchParams.set('page', this.props.page)
    url.searchParams.set('reload', String(Date.now()))
    return <section className="panel page-recovery" role="alert" aria-labelledby="page-recovery-title">
      <h2 id="page-recovery-title">Không mở được {this.props.page === 'leave' ? 'Đăng ký nghỉ' : 'chức năng này'}</h2>
      <p>{this.state.newBuild ? 'Hệ thống đã có bản mới. Hãy cập nhật để mở lại đúng trang này.' : this.state.loadFailure ? 'Không tải được tệp giao diện. Kiểm tra kết nối rồi thử mở lại.' : 'Giao diện gặp lỗi khi hiển thị. Bạn có thể thử mở lại.'}</p>
      <small>Mã lỗi: {this.state.loadFailure ? 'PAGE_MODULE_LOAD' : 'PAGE_RENDER'} · {this.props.page}</small>
      <div className="page-recovery-actions">
        <button type="button" className="primary-button" onClick={this.state.newBuild ? this.update : this.retry}>{this.state.newBuild ? 'Cập nhật và mở lại' : 'Thử mở lại'}</button>
        <a className="secondary-button" href={url.href} target="_blank" rel="noopener noreferrer">Mở bản mới trong tab khác</a>
      </div>
    </section>
  }
}
