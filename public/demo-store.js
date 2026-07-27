/* Client-Side Isolated Demo Store for Nairobi Rentals */
(function() {
  const STORAGE_KEY = 'nrb_demo_store_v1';

  function generateSeedData() {
    const bldg1 = 'demo-bldg-001';
    const bldg2 = 'demo-bldg-002';

    const buildings = [
      { id: bldg1, name: 'Kileleshwa Heights', location: 'Kileleshwa, Nairobi', total_floors: 5, is_demo: true },
      { id: bldg2, name: 'Westlands Court', location: 'Westlands, Nairobi', total_floors: 4, is_demo: true }
    ];

    const unitConfigs = [
      [bldg1, 'A1', 1, 18000, 'occupied', 'u-d1'], [bldg1, 'A2', 1, 18000, 'vacant', 'u-d2'],
      [bldg1, 'B1', 2, 20000, 'occupied', 'u-d3'], [bldg1, 'B2', 2, 20000, 'occupied', 'u-d4'],
      [bldg1, 'C1', 3, 22000, 'occupied', 'u-d5'], [bldg1, 'C2', 3, 22000, 'vacant', 'u-d6'],
      [bldg1, 'D1', 4, 25000, 'occupied', 'u-d7'], [bldg1, 'D2', 4, 25000, 'vacant', 'u-d8'],
      [bldg2, '101', 1, 15000, 'occupied', 'u-d9'], [bldg2, '102', 1, 15000, 'vacant', 'u-d10'],
      [bldg2, '201', 2, 17000, 'occupied', 'u-d11'], [bldg2, '202', 2, 17000, 'occupied', 'u-d12'],
      [bldg2, '301', 3, 19000, 'vacant', 'u-d13'], [bldg2, '302', 3, 19000, 'occupied', 'u-d14'],
      [bldg2, '401', 4, 21000, 'vacant', 'u-d15']
    ];

    const units = unitConfigs.map(([building_id, num, floor, rent, status, id]) => ({
      id,
      building_id,
      unit_number: num,
      floor,
      rent_amount: rent,
      deposit_amount: rent,
      deposit_paid: status === 'occupied',
      status,
      is_active: true,
      is_demo: true
    }));

    const occupiedUnits = units.filter(u => u.status === 'occupied');

    const tenants = [
      { id: 't-d1', unit_id: occupiedUnits[0].id, full_name: 'Amina Wanjiku', phone_number: '+254712345678', email: 'amina.demo@example.com', account_number: 'NRB-001-KH-A1', monthly_rent: occupiedUnits[0].rent_amount, lease_start_date: '2025-01-01', is_active: true, is_approved: true, is_demo: true },
      { id: 't-d2', unit_id: occupiedUnits[1].id, full_name: 'Brian Kamau', phone_number: '+254723456789', email: 'brian.demo@example.com', account_number: 'NRB-001-KH-B1', monthly_rent: occupiedUnits[1].rent_amount, lease_start_date: '2025-02-01', is_active: true, is_approved: true, is_demo: true },
      { id: 't-d3', unit_id: occupiedUnits[2].id, full_name: 'Christine Njeri', phone_number: '+254734567890', email: 'christine.demo@example.com', account_number: 'NRB-001-KH-B2', monthly_rent: occupiedUnits[2].rent_amount, lease_start_date: '2025-03-01', is_active: true, is_approved: true, is_demo: true },
      { id: 't-d4', unit_id: occupiedUnits[3].id, full_name: 'David Ochieng', phone_number: '+254745678901', email: 'david.demo@example.com', account_number: 'NRB-001-KH-C1', monthly_rent: occupiedUnits[3].rent_amount, lease_start_date: '2025-04-01', is_active: true, is_approved: true, is_demo: true },
      { id: 't-d5', unit_id: occupiedUnits[4].id, full_name: 'Esther Achieng', phone_number: '+254756789012', email: 'esther.demo@example.com', account_number: 'NRB-001-WC-101', monthly_rent: occupiedUnits[4].rent_amount, lease_start_date: '2025-05-01', is_active: true, is_approved: true, is_demo: true }
    ];

    const payments = [];
    const statuses = ['approved', 'approved', 'approved', 'approved', 'pending', 'pending', 'rejected', 'rejected'];
    const amounts = [18000, 20000, 20000, 22000, 25000, 15000, 17000, 19000];

    tenants.forEach((tenant, i) => {
      for (let j = 0; j < 2; j++) {
        const idx = i * 2 + j;
        payments.push({
          id: `p-d${idx + 1}`,
          tenant_id: tenant.id,
          unit_id: tenant.unit_id,
          amount_paid: amounts[idx % amounts.length],
          payment_date: `2026-0${(idx % 6) + 1}-05T10:00:00`,
          mpesa_code: `QK${idx}DEMO${Math.floor(1000 + Math.random() * 9000)}`,
          status: statuses[idx % statuses.length],
          rejection_reason: statuses[idx % statuses.length] === 'rejected' ? 'M-Pesa code could not be verified.' : null,
          is_demo: true
        });
      }
    });

    const expenses = [
      { id: 'exp-d1', building_id: bldg1, category: 'Maintenance', amount: 12000, date: '2026-06-15', description: 'Roof repairs — Kileleshwa Heights Block A', is_demo: true },
      { id: 'exp-d2', building_id: bldg1, category: 'Utilities', amount: 8500, date: '2026-06-30', description: 'Nairobi Water bill — June 2026', is_demo: true },
      { id: 'exp-d3', building_id: bldg2, category: 'Security', amount: 15000, date: '2026-06-01', description: 'Guard services — Westlands Court June', is_demo: true },
      { id: 'exp-d4', building_id: bldg2, category: 'Maintenance', amount: 3500, date: '2026-07-02', description: 'Plumbing repair — Unit 201', is_demo: true }
    ];

    return { buildings, units, tenants, payments, expenses };
  }

  window.DemoStore = {
    init() {
      if (!localStorage.getItem(STORAGE_KEY)) {
        this.reset();
      }
    },
    get() {
      try {
        const data = localStorage.getItem(STORAGE_KEY);
        return data ? JSON.parse(data) : this.reset();
      } catch (e) {
        return this.reset();
      }
    },
    save(data) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    },
    reset() {
      const freshData = generateSeedData();
      this.save(freshData);
      return freshData;
    },
    isDemoSession() {
      const user = window.getCurrentUser();
      return user && (user.is_demo || user.id === 'demo-landlord-0000-0000-000000000000' || user.email === 'demo@nairobrentals.com');
    }
  };

  window.DemoStore.init();
})();
