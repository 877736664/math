// 教学素材生成过程中的通用 loading 卡片。

function AssetLoadingCard({ title, description }) {
  return (
    <div className="asset-loading-card" aria-live="polite">
      <p className="asset-loading-title">{title}</p>
      <p className="asset-loading-text">{description}</p>
      <div className="asset-loading-bars" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
    </div>
  )
}

export default AssetLoadingCard
