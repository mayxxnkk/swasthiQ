import { Outlet, NavLink, useLocation } from 'react-router-dom'
import styles from './Layout.module.css'

const NAV_ITEMS = [
  { label: 'Handoff Queue', path: '/queue', icon: '☎' },
]

export default function Layout() {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandIcon}>S</span>
          <span className={styles.brandName}>SwasthiQ</span>
        </div>

        <div className={styles.clinicInfo}>
          <div className={styles.clinicName}>Sunrise Clinic</div>
          <div className={styles.clinicCity}>Dehradun</div>
        </div>

        <nav className={styles.nav}>
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
              }
            >
              <span className={styles.navIcon}>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className={styles.sidebarDots}>
          {[0,1,2,3,4,5].map(i => (
            <div key={i} className={styles.dot} />
          ))}
        </div>
      </aside>

      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
